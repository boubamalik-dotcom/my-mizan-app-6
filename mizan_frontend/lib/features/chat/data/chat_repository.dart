import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';

import '../../../shared/exceptions/network_exception.dart';
import 'chat_message.dart';
import 'chat_remote_data_source.dart';

// Re-exported so the presentation layer can name the room it is showing
// without importing the data source directly — everything above the data
// layer depends on this repository alone.
export 'chat_remote_data_source.dart' show kDefaultChatRoomId;

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
  StreamController<ChatMessage>? _messageController;
  StreamSubscription<dynamic>? _frameSubscription;
  String? _clientId;
  int _unreadCount = 0;

  /// Unread messages received since connecting (or since the last
  /// [markAllAsRead]).
  int get unreadCount => _unreadCount;

  /// Whether a socket is currently open.
  ///
  /// Lets `ChatRoomCubit` reuse the connection the dashboard already
  /// opened instead of reconnecting — a reconnect would replace the
  /// streams the dashboard's `ChatCubit` is listening to, and its badge
  /// would go dark.
  bool get isConnected => _remoteDataSource.isConnected;

  /// Every message relayed to this client while connected, parsed.
  ///
  /// A **broadcast** stream derived from the same single frame
  /// subscription that feeds the unread count: a `WebSocketChannel`'s
  /// stream is single-subscription, so the unread badge and the chat
  /// room cannot each listen to the socket directly — this fans the one
  /// subscription out to both.
  ///
  /// Includes join/leave notices; filtering those out is a presentation
  /// decision, made in `ChatRoomCubit`.
  ///
  /// Emits nothing (rather than failing) when disconnected, so a
  /// listener attached before or after a connection is always safe.
  Stream<ChatMessage> get incomingMessages =>
      (_messageController ??= StreamController<ChatMessage>.broadcast()).stream;

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
        final ChatMessage? message = _parseMessage(frame);
        if (message != null) {
          final StreamController<ChatMessage>? messages = _messageController;
          if (messages != null && !messages.isClosed) messages.add(message);
        }

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

  /// Fetches a room's recent history, oldest first.
  ///
  /// [clientId] must be the caller's own email — the backend mirrors
  /// the socket's identity check and answers **403** otherwise.
  ///
  /// Throws [NetworkException] with a display-ready Arabic message.
  Future<List<ChatMessage>> fetchHistory({
    required String clientId,
    String roomId = kDefaultChatRoomId,
    int limit = 50,
  }) async {
    try {
      return await _remoteDataSource.fetchHistory(
        clientId: clientId,
        roomId: roomId,
        limit: limit,
      );
    } on DioException catch (error) {
      final NetworkException fallback =
          NetworkException.fromDioException(error);
      if (error.response?.statusCode == 403) {
        return Future<List<ChatMessage>>.error(
          NetworkException(
            'لا تملك صلاحية قراءة محادثات هذا المستخدم.',
            statusCode: 403,
            technicalDetail: fallback.technicalDetail,
          ),
        );
      }
      throw fallback;
    }
  }

  /// Posts [content] to the room over the open socket.
  ///
  /// Deliberately does **not** echo the message back to the caller: the
  /// backend persists it and relays it to every participant — including
  /// its author — so it arrives through [incomingMessages] like any
  /// other. Appending it locally as well would show it twice, and would
  /// show it before it was actually stored.
  ///
  /// Throws `ChatConnectionException` when the socket is closed, or
  /// [ArgumentError] for blank content (the caller should not offer to
  /// send nothing).
  void sendMessage(String content) {
    final String trimmed = content.trim();
    if (trimmed.isEmpty) {
      throw ArgumentError.value(content, 'content', 'must not be blank');
    }
    _remoteDataSource.sendMessage(trimmed);
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

  /// Parses [frame] into a [ChatMessage], or `null` if it carries no
  /// message payload.
  ///
  /// Both `"message"` (participant text) and `"system"` (join/leave)
  /// envelopes carry a full message in `data`; `"pong"` and `"error"`
  /// frames do not. A malformed or unparseable frame yields `null`
  /// rather than throwing, so one bad frame cannot kill the stream that
  /// every subsequent message depends on.
  ChatMessage? _parseMessage(dynamic frame) {
    final Map<String, dynamic>? decoded = _decodeFrame(frame);
    if (decoded == null) return null;

    final Object? type = decoded['type'];
    if (type != 'message' && type != 'system') return null;

    final Object? data = decoded['data'];
    if (data is! Map<String, dynamic>) return null;

    try {
      return ChatMessage.fromJson(data);
    } on FormatException {
      return null;
    }
  }

  /// Decodes a raw text frame into a JSON object, or `null` if it is not
  /// one.
  Map<String, dynamic>? _decodeFrame(dynamic frame) {
    if (frame is! String) return null;
    try {
      final Object? decoded = jsonDecode(frame);
      return decoded is Map<String, dynamic> ? decoded : null;
    } catch (_) {
      return null;
    }
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
    final Map<String, dynamic>? decoded = _decodeFrame(frame);
    if (decoded == null) return false;
    if (decoded['type'] != 'message') return false;

    final Object? data = decoded['data'];
    if (data is Map<String, dynamic> && data['sender_id'] == _clientId) {
      return false;
    }
    return true;
  }
}
