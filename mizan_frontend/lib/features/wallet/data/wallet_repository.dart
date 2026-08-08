import 'package:dio/dio.dart';

import '../../../shared/exceptions/network_exception.dart';
import 'wallet_model.dart';
import 'wallet_remote_data_source.dart';

/// Data-layer gateway to `mizan_backend`'s `/wallet` endpoint.
///
/// Mirrors `AuthRepository`'s shape: a plain class, constructor-
/// injected with its data source (defaulting to a shared singleton),
/// returning domain values or throwing [NetworkException] — callers
/// (`WalletCubit`) never see [Dio] or raw JSON.
class WalletRepository {
  WalletRepository({WalletRemoteDataSource? remoteDataSource})
      : _remoteDataSource = remoteDataSource ?? WalletRemoteDataSource();

  /// App-wide singleton, sharing one [WalletRemoteDataSource] (and
  /// therefore one [ApiClient]) with every `WalletCubit`.
  static final WalletRepository instance = WalletRepository();

  final WalletRemoteDataSource _remoteDataSource;

  /// Fetches the authenticated caller's wallet via `GET /wallet`,
  /// automatically provisioning a fresh zero-balance one via
  /// `POST /wallet` the first time they ever reach the dashboard.
  ///
  /// This is the one piece of business logic this feature has: a
  /// **404** from `GET /wallet` means "no wallet yet", which is a
  /// normal, expected condition for a brand-new account — not an
  /// error to surface to the user — so it is caught here and silently
  /// turned into a provisioning call rather than becoming a
  /// [WalletError] the caller would have to special-case itself.
  ///
  /// Throws [NetworkException] for every other failure (including one
  /// raised by the provisioning call itself).
  Future<WalletModel> getOrCreateWallet() async {
    try {
      return await _remoteDataSource.fetchWallet();
    } on DioException catch (error) {
      final NetworkException exception =
          NetworkException.fromDioException(error);
      if (!exception.isNotFound) {
        throw exception;
      }
    }

    try {
      return await _remoteDataSource.createWallet();
    } on DioException catch (error) {
      throw NetworkException.fromDioException(error);
    }
  }

  /// Credits [walletId] by [amount] via `POST /wallet/deposit`,
  /// returning the wallet's new balance as reported by the backend.
  ///
  /// Throws [NetworkException] with a transaction-specific Arabic
  /// message (see [_mapTransactionError]).
  Future<double> deposit({
    required String walletId,
    required double amount,
  }) async {
    try {
      return await _remoteDataSource.deposit(
        walletId: walletId,
        amount: amount,
      );
    } on DioException catch (error) {
      throw _mapTransactionError(error);
    }
  }

  /// Debits [walletId] by [amount] via `POST /wallet/withdraw`.
  Future<double> withdraw({
    required String walletId,
    required double amount,
  }) async {
    try {
      return await _remoteDataSource.withdraw(
        walletId: walletId,
        amount: amount,
      );
    } on DioException catch (error) {
      throw _mapTransactionError(error);
    }
  }

  /// Moves [amount] from [sourceWalletId] to [destinationWalletId] via
  /// `POST /wallet/transfer`, returning the source wallet's new
  /// balance.
  ///
  /// [destinationWalletId] is a **wallet id**, not a user id or email:
  /// the backend performs no user lookup (see
  /// `ApiEndpoints.walletTransfer`).
  Future<double> transfer({
    required String sourceWalletId,
    required String destinationWalletId,
    required double amount,
  }) async {
    try {
      return await _remoteDataSource.transfer(
        sourceWalletId: sourceWalletId,
        destinationWalletId: destinationWalletId,
        amount: amount,
      );
    } on DioException catch (error) {
      throw _mapTransactionError(error);
    }
  }

  // -- Error mapping ------------------------------------------------------

  /// Translates the specific status codes
  /// `WalletController._translate_domain_errors` uses for money
  /// operations into precise Arabic messages, so the user is told what
  /// actually went wrong instead of a generic "request failed".
  ///
  /// Mapping (mirrors the backend's own):
  ///
  ///  * **400** `InsufficientFundsError` -> "الرصيد غير كافٍ"
  ///  * **422** `InvalidTransactionAmountError` -> invalid amount
  ///  * **423** `WalletLockedError` -> wallet frozen
  ///  * **404** `WalletNotFoundError` -> wallet (often the transfer
  ///    destination) does not exist
  ///  * **403** ownership violation -> not your wallet
  ///  * **409** optimistic-lock conflict -> safe to retry
  ///
  /// Anything else falls back to
  /// [NetworkException.fromDioException]'s generic-by-status mapping
  /// (timeouts, offline, 5xx).
  NetworkException _mapTransactionError(DioException error) {
    final NetworkException fallback = NetworkException.fromDioException(error);
    final String? message = switch (error.response?.statusCode) {
      400 => 'الرصيد غير كافٍ لإتمام هذه العملية.',
      403 => 'لا تملك صلاحية التصرف في هذه المحفظة.',
      404 => 'لم يتم العثور على المحفظة المطلوبة. يرجى التحقق من المعرّف.',
      409 => 'تم تعديل المحفظة من عملية أخرى. يرجى المحاولة مرة أخرى.',
      422 => 'المبلغ المدخل غير صالح. يجب أن يكون أكبر من صفر.',
      423 => 'هذه المحفظة مقفلة مؤقتًا ولا يمكن إجراء عمليات عليها.',
      _ => null,
    };

    if (message == null) return fallback;
    return NetworkException(
      message,
      statusCode: fallback.statusCode,
      technicalDetail: fallback.technicalDetail,
    );
  }
}
