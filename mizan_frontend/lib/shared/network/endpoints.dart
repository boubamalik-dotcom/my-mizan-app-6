/// Central catalog of the `mizan_backend` REST surface this app talks
/// to, so a path never needs to be retyped (and risk drifting from the
/// backend) at every call site.
class ApiEndpoints {
  const ApiEndpoints._();

  /// The backend's base URL, including its `/api/v1` prefix (see
  /// `mizan_backend/main.py`).
  ///
  /// Defaults to the standard Android emulator alias for the host
  /// machine's `localhost` (`10.0.2.2`) during local development.
  /// Override at build time for a real device, iOS simulator, or a
  /// deployed backend, e.g.:
  ///
  /// ```
  /// flutter run --dart-define=API_BASE_URL=https://api.mizan.app/api/v1
  /// ```
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000/api/v1',
  );

  // -- Authentication ---------------------------------------------------

  static const String register = '/auth/register';
  static const String login = '/auth/login';
  static const String me = '/auth/me';

  // -- Wallet -------------------------------------------------------------

  /// `GET` fetches the authenticated caller's own wallet (**404** if
  /// they have not provisioned one yet); `POST` provisions a new one.
  /// See `WalletRepository.getOrCreateWallet` for how the two are
  /// combined into a single "get, or create on first use" call.
  static const String wallet = '/wallet';

  // -- Chat (WebSocket) ---------------------------------------------------

  /// [baseUrl] with its scheme swapped for the WebSocket equivalent
  /// (`http` -> `ws`, `https` -> `wss`), so the socket endpoint always
  /// follows the same host/port/prefix — and the same
  /// `--dart-define=API_BASE_URL` override — as every REST call.
  static String get webSocketBaseUrl =>
      baseUrl.replaceFirst(RegExp('^http'), 'ws');

  /// Builds the chat socket URI for `clientId`.
  ///
  /// The backend (`mizan_backend/src/layer_2_api/routes/chat_routes.py`)
  /// requires all three parts:
  ///
  ///  * `clientId` in the path — which must equal the JWT's subject
  ///    (the user's email), or the connection is closed with
  ///    `WS_1008_POLICY_VIOLATION`. It is percent-encoded here since
  ///    an email's `@` is not a legal raw path character.
  ///  * `room_id` — mandatory, no server-side default.
  ///  * `token` — the JWT, passed as a query parameter because browser
  ///    `WebSocket` APIs cannot send an `Authorization` header.
  static Uri chatWebSocket({
    required String clientId,
    required String roomId,
    required String token,
  }) {
    return Uri.parse(
      '$webSocketBaseUrl/chat/ws/chat/${Uri.encodeComponent(clientId)}',
    ).replace(
      queryParameters: <String, String>{'room_id': roomId, 'token': token},
    );
  }
}
