import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import 'endpoints.dart';
import 'interceptors.dart';
import 'token_storage.dart';

/// The app's single HTTP client for talking to `mizan_backend`.
///
/// Every feature repository (`AuthRepository`, and the Wallet/Chat
/// repositories that will follow it) goes through this class instead
/// of constructing its own [Dio] instance, so:
///
///  * the base URL is configured exactly once ([ApiEndpoints.baseUrl]);
///  * every request automatically carries the caller's JWT, via
///    [AuthInterceptor], without any repository needing to read
///    [TokenStorage] itself just to attach a header;
///  * a `401` from a protected endpoint is handled globally — the
///    token is cleared and the user is bounced back to the login
///    screen — instead of every repository having to special-case it.
class ApiClient {
  ApiClient({Dio? dio, TokenStorage? tokenStorage})
      : tokenStorage = tokenStorage ?? TokenStorage.instance,
        dio = dio ?? Dio(_baseOptions) {
    this.dio.interceptors.add(AuthInterceptor(tokenStorage: this.tokenStorage));
    if (kDebugMode) {
      this.dio.interceptors.add(
            LogInterceptor(
              requestBody: true,
              responseBody: true,
              logPrint: (Object log) => debugPrint('[ApiClient] $log'),
            ),
          );
    }
  }

  /// App-wide singleton, sharing one connection pool and one set of
  /// interceptors across every repository.
  static final ApiClient instance = ApiClient();

  final Dio dio;
  final TokenStorage tokenStorage;

  static BaseOptions get _baseOptions => BaseOptions(
        baseUrl: ApiEndpoints.baseUrl,
        connectTimeout: const Duration(seconds: 15),
        receiveTimeout: const Duration(seconds: 15),
        sendTimeout: const Duration(seconds: 15),
        headers: const <String, String>{'Content-Type': 'application/json'},
        // Dio's default `validateStatus` (2xx only) is kept
        // deliberately unchanged: a non-2xx response still throws a
        // `DioException`, but that exception's `.response` is still
        // fully populated with the backend's JSON body (e.g.
        // `{"detail": "..."}`) — nothing here needs to widen
        // `validateStatus` just to read it. This also keeps every 4xx
        // reaching `AuthInterceptor.onError`, which is what lets a
        // `401` trigger the global logout redirect.
      );

  /// `GET` — see [Dio.get].
  Future<Response<dynamic>> get(
    String path, {
    Map<String, dynamic>? queryParameters,
  }) {
    return dio.get<dynamic>(path, queryParameters: queryParameters);
  }

  /// `POST` — see [Dio.post].
  Future<Response<dynamic>> post(String path, {dynamic data}) {
    return dio.post<dynamic>(path, data: data);
  }

  /// `PUT` — see [Dio.put].
  Future<Response<dynamic>> put(String path, {dynamic data}) {
    return dio.put<dynamic>(path, data: data);
  }

  /// `DELETE` — see [Dio.delete].
  Future<Response<dynamic>> delete(String path, {dynamic data}) {
    return dio.delete<dynamic>(path, data: data);
  }
}
