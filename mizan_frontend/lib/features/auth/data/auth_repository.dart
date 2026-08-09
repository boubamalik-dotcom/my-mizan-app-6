import 'package:dio/dio.dart';

import '../../../shared/exceptions/network_exception.dart';
import '../../../shared/network/api_client.dart';
import '../../../shared/network/endpoints.dart';
import '../../../shared/network/token_storage.dart';
import '../domain/entities/auth_user.dart';

/// Data-layer gateway to `mizan_backend`'s `/auth/*` endpoints.
///
/// Every public method here either returns a plain domain value
/// ([AuthUser], `void`) or throws a [NetworkException] — callers
/// (the login/register pages) never need to know about [Dio] or
/// parse an HTTP response themselves.
class AuthRepository {
  AuthRepository({ApiClient? apiClient, TokenStorage? tokenStorage})
      : _apiClient = apiClient ?? ApiClient.instance,
        _tokenStorage = tokenStorage ?? TokenStorage.instance;

  /// App-wide singleton — the login/register pages share this one
  /// instance (and therefore one [ApiClient]/[TokenStorage] pair)
  /// rather than each constructing their own.
  static final AuthRepository instance = AuthRepository();

  final ApiClient _apiClient;
  final TokenStorage _tokenStorage;

  /// Registers a new account via `POST /auth/register`.
  ///
  /// Does *not* log the new user in — the backend's register endpoint
  /// only creates the account and returns its public profile; call
  /// [login] afterwards (or let the caller decide) to obtain a
  /// session token.
  ///
  /// Throws [NetworkException] on failure, most notably with
  /// [NetworkException.isConflict]-like semantics (backend returns
  /// **400**, not 409, for this specific case — see the field's own
  /// documentation) when [email] is already registered.
  Future<AuthUser> register({
    required String fullName,
    required String email,
    required String password,
  }) async {
    try {
      final Response<dynamic> response = await _apiClient.post(
        ApiEndpoints.register,
        data: <String, String>{
          'email': email.trim(),
          'password': password,
          'full_name': fullName.trim(),
        },
      );
      return AuthUser.fromJson(response.data as Map<String, dynamic>);
    } on DioException catch (error) {
      throw _mapRegisterError(error);
    }
  }

  /// Authenticates against `POST /auth/login` and, on success,
  /// securely persists the returned JWT via [TokenStorage] — every
  /// subsequent request made through [ApiClient] will then
  /// automatically carry it (see `AuthInterceptor`).
  ///
  /// Throws [NetworkException] on failure — most notably a **401**
  /// for an incorrect email/password combination.
  Future<void> login({required String email, required String password}) async {
    final Response<dynamic> response;
    try {
      response = await _apiClient.post(
        ApiEndpoints.login,
        data: <String, String>{'email': email.trim(), 'password': password},
      );
    } on DioException catch (error) {
      throw _mapLoginError(error);
    }

    final String accessToken =
        (response.data as Map<String, dynamic>)['access_token'] as String;
    // Saved *outside* the try/catch above: a `StorageException` here
    // is a different failure mode (the login itself succeeded; only
    // persisting its result did not) and should propagate as-is
    // rather than being mislabeled as a login/credentials error.
    await _tokenStorage.saveToken(accessToken);
  }

  /// Fetches the currently authenticated user's profile via
  /// `GET /auth/me`. Useful for populating a profile screen, or for
  /// confirming a locally-stored token is still actually valid.
  ///
  /// Throws [NetworkException] — notably a **401** if the stored
  /// token has expired or been revoked (in which case
  /// `AuthInterceptor` will already have cleared it and redirected to
  /// the login screen by the time this call's `Future` resolves).
  Future<AuthUser> getCurrentUser() async {
    try {
      final Response<dynamic> response = await _apiClient.get(ApiEndpoints.me);
      return AuthUser.fromJson(response.data as Map<String, dynamic>);
    } on DioException catch (error) {
      throw NetworkException.fromDioException(error);
    }
  }

  /// Whether a session token is currently stored on this device — a
  /// fast, local, offline check used to decide the app's start-up
  /// route (see `LoginPage`). Does not confirm the token is still
  /// valid; an expired token is only ever detected by the backend
  /// rejecting an actual request.
  Future<bool> isLoggedIn() => _tokenStorage.hasToken();

  /// Clears the locally-stored session token, signing the user out on
  /// this device. The backend issues stateless JWTs, so there is
  /// nothing to invalidate server-side — this is purely local.
  Future<void> logout() => _tokenStorage.clearToken();

  // -- Error mapping ------------------------------------------------------

  /// `POST /auth/register` only ever fails its business rules one way
  /// — a **400** for an email that is already registered (see
  /// `AuthController.register` in `mizan_backend`) — so that one case
  /// gets a precise, Arabic message; everything else falls back to
  /// [NetworkException.fromDioException]'s generic-by-status mapping.
  NetworkException _mapRegisterError(DioException error) {
    if (error.response?.statusCode == 400) {
      return NetworkException(
        'هذا البريد الإلكتروني مسجّل بالفعل. يرجى تسجيل الدخول بدلاً من ذلك.',
        statusCode: 400,
        technicalDetail:
            NetworkException.fromDioException(error).technicalDetail,
      );
    }
    return NetworkException.fromDioException(error);
  }

  /// `POST /auth/login` returns a **401** for *any* invalid
  /// email/password combination — including an unregistered email —
  /// by design, so as not to reveal which part was wrong (see
  /// `AuthController.login`). This mirrors that with one precise,
  /// combined Arabic message rather than the generic 401 default.
  NetworkException _mapLoginError(DioException error) {
    if (error.response?.statusCode == 401) {
      return NetworkException(
        'البريد الإلكتروني أو كلمة المرور غير صحيحة.',
        statusCode: 401,
        technicalDetail:
            NetworkException.fromDioException(error).technicalDetail,
      );
    }
    return NetworkException.fromDioException(error);
  }
}
