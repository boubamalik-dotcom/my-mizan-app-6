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
}
