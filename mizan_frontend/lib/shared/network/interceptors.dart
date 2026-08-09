import 'package:dio/dio.dart';
import 'package:flutter/widgets.dart';

import 'token_storage.dart';

/// Route name for the login screen.
///
/// Defined here — in the dependency-free `shared` layer — rather than
/// in `core/core_navigator.dart`, because [AuthInterceptor] (below)
/// needs it to force a redirect after a `401`, and `shared/` must
/// never depend on `core/` (see the layering note on
/// `MiniProgramPlaceholderPage`). `CoreRoutes.login` in
/// `core_navigator.dart` is defined as this exact constant, so there
/// remains a single source of truth for the route name even though
/// `core/` (which *is* allowed to depend on `shared/`) owns the actual
/// routing table.
const String kLoginRouteName = '/auth/login';

/// Global [Navigator] key installed on the app's `MaterialApp` (see
/// `main.dart`) so code that has no [BuildContext] of its own — like
/// [AuthInterceptor], which runs inside Dio's request/response
/// pipeline — can still navigate, e.g. to force a logout redirect
/// after a session-ending `401 Unauthorized`.
final GlobalKey<NavigatorState> rootNavigatorKey = GlobalKey<NavigatorState>();

/// Attaches the caller's JWT to every outgoing request (when one is
/// stored) and reacts to a `401 Unauthorized` response by clearing it
/// and forcing the user back to the login screen.
///
/// This is the app's single point of session enforcement: no
/// repository or BLoC needs to manually attach a header or notice an
/// expired session — every request made through [ApiClient] passes
/// through here automatically.
class AuthInterceptor extends Interceptor {
  AuthInterceptor({TokenStorage? tokenStorage})
      : _tokenStorage = tokenStorage ?? TokenStorage.instance;

  final TokenStorage _tokenStorage;

  static const String _authorizationHeader = 'Authorization';

  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    final String? token = await _tokenStorage.readToken();
    if (token != null) {
      options.headers[_authorizationHeader] = 'Bearer $token';
    }
    handler.next(options);
  }

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    final bool requestWasAuthenticated =
        err.requestOptions.headers.containsKey(_authorizationHeader);

    // Only an *authenticated* request being rejected as unauthorized
    // means the session itself is no longer valid — e.g. the token
    // expired, or the account was deactivated. A `401` from a public
    // endpoint (wrong password on `POST /auth/login`, for instance)
    // never carried a token in the first place and must be left alone
    // here so the caller's own error handling (a "wrong password"
    // message on the login form) still runs.
    if (err.response?.statusCode == 401 && requestWasAuthenticated) {
      await _tokenStorage.clearToken();
      rootNavigatorKey.currentState?.pushNamedAndRemoveUntil(
        kLoginRouteName,
        (Route<dynamic> route) => false,
        arguments: LoginRedirectReason.sessionExpired,
      );
    }

    handler.next(err);
  }
}

/// Why the user was redirected to the login screen, passed as the
/// route's `arguments` so [LoginPage] can show a matching message
/// (e.g. "your session has expired") instead of a bare, unexplained
/// login form.
enum LoginRedirectReason { sessionExpired }
