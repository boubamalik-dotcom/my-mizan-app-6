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

  /// `POST` — credits a wallet. Body: `{wallet_id, amount}`.
  static const String walletDeposit = '/wallet/deposit';

  /// `POST` — debits a wallet. Body: `{wallet_id, amount}`.
  static const String walletWithdraw = '/wallet/withdraw';

  /// `POST` — moves funds between two wallets. Body:
  /// `{source_wallet_id, destination_wallet_id, amount}`.
  ///
  /// Note the destination is a **wallet id**, not a user id or email:
  /// the backend's `TransferRequest`
  /// (`layer_2_api/schemas/wallet_schemas.py`) has no user-lookup step,
  /// so the caller must already know the recipient's wallet id.
  static const String walletTransfer = '/wallet/transfer';

  // -- Oran Real Estate ---------------------------------------------------

  /// `GET` — property listings, optionally narrowed by repeated
  /// `amenities` query parameters.
  ///
  /// Not implemented in `mizan_backend` yet: `PropertyRepository` falls
  /// back to a bundled showcase catalogue while this 404s, and switches
  /// to live data the moment the endpoint ships.
  static const String properties = '/properties';

  // -- Mizan Door (clinic queues) -----------------------------------------

  /// `GET` — every clinic's current queue, plus the caller's own
  /// reservation if they hold one.
  ///
  /// Not implemented in `mizan_backend` yet: `QueueRepository` falls
  /// back to a bundled showcase catalogue while this 404s, and switches
  /// to live data the moment the endpoint ships.
  static const String clinicQueues = '/queues';

  /// `POST` — take a place in a clinic's queue.
  static String joinClinicQueue(String clinicId) =>
      '/queues/${Uri.encodeComponent(clinicId)}/reservations';

  /// `DELETE` — give up a reservation.
  static String clinicReservation(String reservationId) =>
      '/queues/reservations/${Uri.encodeComponent(reservationId)}';

  /// The live-updates socket for one clinic's queue.
  ///
  /// The server pushes a frame whenever that clinic's queue changes —
  /// someone joins, someone cancels, or reception calls the next
  /// patient. The frame carries the clinic's aggregate state only
  /// (`waiting_count`, `now_serving_ticket`, …) and **nothing about any
  /// patient**, so a client wanting its own position still reads
  /// `GET /queues` with its token.
  ///
  /// `token` goes in the query string because browser `WebSocket` APIs
  /// cannot send an `Authorization` header — the same reason the chat
  /// socket does it.
  static Uri clinicQueueWebSocket({
    required String clinicId,
    required String token,
  }) {
    return Uri.parse(
      '$webSocketBaseUrl/queues/ws/${Uri.encodeComponent(clinicId)}'
      '?token=${Uri.encodeQueryComponent(token)}',
    );
  }

  // -- Chat (REST) --------------------------------------------------------

  /// `GET` — a room's recent messages, oldest first. Requires a
  /// `room_id` query parameter (no server-side default) and an optional
  /// `limit` (1-200, default 50).
  ///
  /// [clientId] must be the authenticated caller's own email, exactly
  /// as for the socket: the backend rejects a mismatch with **403**
  /// before reading any history. It is percent-encoded because an
  /// email's `@` is not a legal raw path character.
  static String chatHistory(String clientId) =>
      '/chat/history/${Uri.encodeComponent(clientId)}';

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
