import 'package:dio/dio.dart';

import '../../../shared/network/api_client.dart';
import '../../../shared/network/endpoints.dart';
import 'wallet_model.dart';

/// Thin, direct wrapper over [ApiClient] for the Digital Wallet's
/// `/wallet` endpoint — the only place in the Wallet feature that
/// touches [Dio] or raw JSON. `WalletRepository` is its sole caller,
/// and is what translates its [DioException]s into domain-level
/// behavior (see `WalletRepository.getOrCreateWallet`'s
/// auto-provisioning on a 404).
class WalletRemoteDataSource {
  WalletRemoteDataSource({ApiClient? apiClient})
      : _apiClient = apiClient ?? ApiClient.instance;

  final ApiClient _apiClient;

  /// `GET /wallet` — the authenticated caller's own wallet.
  ///
  /// Throws the raw [DioException] on failure, most notably a **404**
  /// when the user has not provisioned a wallet yet.
  Future<WalletModel> fetchWallet() async {
    final Response<dynamic> response =
        await _apiClient.get(ApiEndpoints.wallet);
    return WalletModel.fromJson(response.data as Map<String, dynamic>);
  }

  /// `POST /wallet` — provisions a new, zero-balance, unlocked wallet
  /// for the authenticated caller.
  Future<WalletModel> createWallet({String currency = 'DZD'}) async {
    final Response<dynamic> response = await _apiClient.post(
      ApiEndpoints.wallet,
      data: <String, String>{'currency': currency},
    );
    return WalletModel.fromJson(response.data as Map<String, dynamic>);
  }

  /// `POST /wallet/deposit` — credits [walletId] by [amount].
  ///
  /// Returns the wallet's new balance, as reported by the backend's
  /// `TransactionResponse` — never a locally-computed figure, so the
  /// UI always mirrors the server's immutable ledger.
  Future<double> deposit({
    required String walletId,
    required double amount,
  }) async {
    final Response<dynamic> response = await _apiClient.post(
      ApiEndpoints.walletDeposit,
      data: <String, String>{
        'wallet_id': walletId,
        'amount': formatAmount(amount),
      },
    );
    return _newBalanceOf(response.data, 'new_balance');
  }

  /// `POST /wallet/withdraw` — debits [walletId] by [amount].
  Future<double> withdraw({
    required String walletId,
    required double amount,
  }) async {
    final Response<dynamic> response = await _apiClient.post(
      ApiEndpoints.walletWithdraw,
      data: <String, String>{
        'wallet_id': walletId,
        'amount': formatAmount(amount),
      },
    );
    return _newBalanceOf(response.data, 'new_balance');
  }

  /// `POST /wallet/transfer` — moves [amount] from [sourceWalletId] to
  /// [destinationWalletId], returning the *source* wallet's new
  /// balance (the only side of the transfer this user owns).
  Future<double> transfer({
    required String sourceWalletId,
    required String destinationWalletId,
    required double amount,
  }) async {
    final Response<dynamic> response = await _apiClient.post(
      ApiEndpoints.walletTransfer,
      data: <String, String>{
        'source_wallet_id': sourceWalletId,
        'destination_wallet_id': destinationWalletId,
        'amount': formatAmount(amount),
      },
    );
    return _newBalanceOf(response.data, 'new_source_balance');
  }

  /// Serializes [amount] as a decimal *string* rather than a JSON
  /// number.
  ///
  /// The backend models money as `Decimal` (`Numeric(18, 4)`) and its
  /// own schema examples pass amounts as strings for exactly this
  /// reason: a JSON float can't represent every decimal value
  /// exactly, so sending `0.1 + 0.2` as a number risks handing the
  /// ledger `0.30000000000000004`. Four decimal places matches the
  /// column's scale; trailing zeros are trimmed purely for readable
  /// request bodies.
  static String formatAmount(double amount) {
    final String fixed = amount.toStringAsFixed(4);
    if (!fixed.contains('.')) return fixed;
    return fixed.replaceFirst(RegExp(r'\.?0+$'), '');
  }

  /// Reads a balance field out of a transaction response, accepting a
  /// JSON number or a numeric string (the backend serializes
  /// `Decimal`, so both shapes are plausible across versions).
  static double _newBalanceOf(dynamic data, String field) {
    if (data is! Map<String, dynamic>) {
      throw FormatException('Unexpected transaction response: $data');
    }
    final Object? value = data[field];
    if (value is num) return value.toDouble();
    if (value is String) return double.parse(value);
    throw FormatException('Expected a numeric `$field`, got: $value');
  }
}
