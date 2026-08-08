import 'dart:async';
import 'dart:convert';

import 'chat_remote_data_source.dart';

/// Data-layer gateway to the real-time Chat engine.
///
/// Mirrors `WalletRepository`/`AuthRepository`'s shape: a plain class,
/// constructor-injected with its data source, exposing domain values
/// (here: a running unread count) rather than raw frames — `ChatCubit`
/// never parses JSON or touches a `WebSocketChannel`.
///
/// Owning the unread count here (rather than in the cubit) keeps the
/// rule for *what counts as unread* — an incoming chat message from
/// someone else, not a join/leave notice, not a `pong`, and not the
/// echo of the user's own message — in one testable place.
class ChatRepository {
  ChatRepository({ChatRemoteDataSource? remoteDataSource})
      : _remoteDataSource = remoteDataSource ?? ChatRemoteDataSource();

  /// App-wide singleton, so every `ChatCubit` shares one socket.
  static final ChatRepository instance = ChatRepository();

  final ChatRemoteDataSource _remoteDataSource;

  StreamController<int>? _unreadController;
  StreamSubscription<dynamic>? _frameSubscription;
  String? _clientId;
  int _unreadCount = 0;

  /// Unread messages received since connecting (or since the last
  /// [markAllAsRead]).
  int get unreadCount => _unreadCount;

  /// Connects the chat socket as [clientId] (the user's email — see
  /// [ChatRemoteDataSource.connect]) and returns a stream of the
  /// running unread count.
  ///
  /// The returned stream mirrors the socket's own lifecycle, which is
  /// what lets `ChatCubit` map it straight onto its states:
  ///
  ///  * a new value on every unread message -> `ChatConnected`;
  ///  * `onDone` when the server or network closes the socket ->
  ///    `ChatDisconnected`;
  ///  * `onError` for a socket-level failure -> `ChatError`.
  ///
  /// Throws `ChatConnectionException` if the handshake cannot even be
  /// attempted (e.g. no stored token).
  Future<Stream<int>> connect({required String clientId}) async {
    await disconnect();

    final Stream<dynamic> frames = await _remoteDataSource.connect(clientId);

    _clientId = clientId;
    _unreadCount = 0;
    final StreamController<int> controller = StreamController<int>.broadcast();
    _unreadController = controller;

    _frameSubscription = frames.listen(
      (dynamic frame) {
        if (_countsAsUnread(frame)) {
          _unreadCount++;
          if (!controller.isClosed) controller.add(_unreadCount);
        }
      },
      onError: (Object error, StackTrace stackTrace) {
        if (!controller.isClosed) controller.addError(error, stackTrace);
      },
      onDone: () {
        if (!controller.isClosed) controller.close();
      },
      cancelOnError: false,
    );

    return controller.stream;
  }

  /// Resets the unread count to zero (e.g. once the user opens the
  /// chat screen) and publishes the reset so the badge disappears.
  void markAllAsRead() {
    _unreadCount = 0;
    final StreamController<int>? controller = _unreadController;
    if (controller != null && !controller.isClosed) {
      controller.add(_unreadCount);
    }
  }

  /// Tears the connection down: cancels the frame subscription,
  /// closes the socket, and closes the unread stream.
  ///
  /// Called by `ChatCubit.close()` — which `BlocProvider` invokes when
  /// the dashboard is disposed, including when a logout (or the
  /// `AuthInterceptor`'s forced 401 redirect) replaces the navigation
  /// stack — so the socket never outlives the session that authorized
  /// it. Safe to call repeatedly.
  Future<void> disconnect() async {
    await _frameSubscription?.cancel();
    _frameSubscription = null;

    await _remoteDataSource.disconnect();

    final StreamController<int>? controller = _unreadController;
    _unreadController = null;
    if (controller != null && !controller.isClosed) {
      await controller.close();
    }

    _clientId = null;
    _unreadCount = 0;
  }

  /// Whether [frame] is an incoming chat message that should bump the
  /// unread badge.
  ///
  /// The backend wraps every server -> client frame as
  /// `{"type": "message" | "system" | "pong" | "error", "data": {...}}`
  /// (see `chat_routes.py`'s protocol docs). Only `"message"` frames
  /// count, and only from *another* participant: the backend
  /// deliberately delivers the sender their own message back through
  /// the same broker relay, which must not be counted as unread.
  /// Malformed frames are ignored rather than crashing the stream.
  bool _countsAsUnread(dynamic frame) {
    if (frame is! String) return false;

    final Object? decoded;
    try {
      decoded = jsonDecode(frame);
    } catch (_) {
      return false;
    }

    if (decoded is! Map<String, dynamic>) return false;
    if (decoded['type'] != 'message') return false;

    final Object? data = decoded['data'];
    if (data is Map<String, dynamic> && data['sender_id'] == _clientId) {
      return false;
    }
    return true;
  }
}
