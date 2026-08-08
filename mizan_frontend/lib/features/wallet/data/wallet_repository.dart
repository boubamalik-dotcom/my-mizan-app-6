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
}
