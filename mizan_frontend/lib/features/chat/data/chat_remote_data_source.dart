import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:web_socket_channel/status.dart' as ws_status;
import 'package:web_socket_channel/web_socket_channel.dart';

import '../../../shared/network/api_client.dart';
import '../../../shared/network/endpoints.dart';
import '../../../shared/network/token_storage.dart';
import 'chat_exceptions.dart';
import 'chat_message.dart';

/// Builds a [WebSocketChannel] for [uri]. Injected so tests can supply
/// a fake channel instead of opening a real socket.
typedef WebSocketChannelFactory = WebSocketChannel Function(Uri uri);

/// The room every dashboard connection joins for now.
///
/// The backend requires a `room_id` on every socket (there is no
/// server-side default), but the app has no per-conversation UI yet —
/// so until real room/conversation management lands, all clients share
/// this one well-known room. Named rather than inlined so that change
/// is a one-line edit.
const String kDefaultChatRoomId = 'general';

/// Owns the Chat transport — the raw WebSocket plus the REST history
/// call. The only place in the Chat feature that touches
/// `web_socket_channel`, [Dio], or the wire format.
///
/// `ChatRepository` is its sole caller and is what turns what this
/// exposes into domain values (an unread count, a message list).
class ChatRemoteDataSource {
  ChatRemoteDataSource({
    TokenStorage? tokenStorage,
    WebSocketChannelFactory? channelFactory,
    ApiClient? apiClient,
  })  : _tokenStorage = tokenStorage ?? TokenStorage.instance,
        _channelFactory = channelFactory ?? WebSocketChannel.connect,
        _apiClient = apiClient ?? ApiClient.instance;

  final TokenStorage _tokenStorage;
  final WebSocketChannelFactory _channelFactory;
  final ApiClient _apiClient;

  WebSocketChannel? _channel;

  /// Whether a channel is currently open.
  bool get isConnected => _channel != null;

  /// Opens the chat socket as [clientId] and returns its incoming
  /// frame stream.
  ///
  /// The JWT is read from [TokenStorage] and appended as a `?token=`
  /// query parameter (see [ApiEndpoints.chatWebSocket]) — browser
  /// `WebSocket` APIs cannot send an `Authorization` header, so this
  /// is how the backend authenticates the handshake.
  ///
  /// [clientId] must be the authenticated user's email: the backend
  /// closes any connection whose `client_id` does not match the
  /// token's subject.
  ///
  /// The returned stream is single-subscription (it is the channel's
  /// own), so exactly one listener — `ChatRepository` — may consume it.
  ///
  /// Throws [ChatConnectionException] if no token is stored (the user
  /// is not logged in) or the handshake itself fails.
  Future<Stream<dynamic>> connect(
    String clientId, {
    String roomId = kDefaultChatRoomId,
  }) async {
    await disconnect();

    final String? token = await _tokenStorage.readToken();
    if (token == null) {
      throw const ChatConnectionException(
        'يجب تسجيل الدخول أولاً لبدء الدردشة.',
      );
    }

    final Uri uri = ApiEndpoints.chatWebSocket(
      clientId: clientId,
      roomId: roomId,
      token: token,
    );

    try {
      final WebSocketChannel channel = _channelFactory(uri);
      _channel = channel;
      return channel.stream;
    } catch (error) {
      _channel = null;
      throw ChatConnectionException(
        'تعذّر الاتصال بخدمة الدردشة.',
        cause: error,
      );
    }
  }

  /// Sends a raw frame to the server. Silently ignored when no channel
  /// is open, so callers never need to check [isConnected] first.
  void send(String frame) {
    _channel?.sink.add(frame);
  }

  /// Posts [content] to the room as a chat message.
  ///
  /// The backend's client -> server envelope is
  /// `{"type": "message", "content": "..."}` (see `chat_routes.py`'s
  /// protocol docs); `type` is the discriminator that distinguishes a
  /// message from a `ping` keep-alive.
  ///
  /// Throws [ChatConnectionException] when no socket is open, so a
  /// message is never silently dropped — the caller can tell the user
  /// it did not send.
  void sendMessage(String content) {
    if (!isConnected) {
      throw const ChatConnectionException(
        'لا يوجد اتصال بخدمة الدردشة. لم يتم إرسال الرسالة.',
      );
    }
    send(jsonEncode(<String, String>{'type': 'message', 'content': content}));
  }

  /// `GET /chat/history/{clientId}?room_id=…&limit=…` — the room's most
  /// recent messages, oldest first.
  ///
  /// [clientId] must be the caller's own email; the backend answers
  /// **403** for anyone else's (it mirrors the socket's identity check).
  /// Throws the raw [DioException] on failure, for `ChatRepository` to
  /// translate.
  Future<List<ChatMessage>> fetchHistory({
    required String clientId,
    String roomId = kDefaultChatRoomId,
    int limit = 50,
  }) async {
    final Response<dynamic> response = await _apiClient.get(
      ApiEndpoints.chatHistory(clientId),
      queryParameters: <String, dynamic>{'room_id': roomId, 'limit': limit},
    );

    final dynamic body = response.data;
    if (body is! Map<String, dynamic>) {
      throw FormatException('Unexpected chat history response: $body');
    }

    final Object? messages = body['messages'];
    if (messages is! List) {
      throw FormatException('Expected a `messages` list, got: $messages');
    }

    return messages
        .cast<Map<String, dynamic>>()
        .map(ChatMessage.fromJson)
        .toList(growable: false);
  }

  /// Forgets the channel after its stream has already terminated.
  ///
  /// [isConnected] is what callers use to decide whether they may send,
  /// so a channel that can no longer deliver anything must stop
  /// counting as connected. Without this the dead channel lingered:
  /// `ChatRoomCubit` skipped reconnecting because it believed a socket
  /// was up, left its composer enabled, and [sendMessage] wrote into a
  /// closed sink instead of reporting that the message had not been
  /// sent.
  ///
  /// Distinct from [disconnect], which *initiates* a closure; this only
  /// records one that already happened.
  void markDisconnected() {
    _channel = null;
  }

  /// Closes the channel (normal closure) and releases it.
  ///
  /// Safe to call when already disconnected, and safe to call twice —
  /// which matters because both `ChatRepository.disconnect` (on logout
  /// or when the dashboard is disposed) and a fresh [connect] call
  /// invoke it.
  Future<void> disconnect() async {
    final WebSocketChannel? channel = _channel;
    _channel = null;
    if (channel == null) return;
    try {
      await channel.sink.close(ws_status.normalClosure);
    } catch (_) {
      // A socket that is already dead (dropped connection, app being
      // torn down) throws on close; there is nothing left to clean up
      // in that case, and failing to close is never worth surfacing.
    }
  }
}
