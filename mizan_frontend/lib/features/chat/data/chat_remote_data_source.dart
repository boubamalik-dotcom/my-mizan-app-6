import 'package:web_socket_channel/status.dart' as ws_status;
import 'package:web_socket_channel/web_socket_channel.dart';

import '../../../shared/network/endpoints.dart';
import '../../../shared/network/token_storage.dart';
import 'chat_exceptions.dart';

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

/// Owns the raw Chat WebSocket — the only place in the Chat feature
/// that touches `web_socket_channel` or the socket URI.
///
/// `ChatRepository` is its sole caller and is what turns the raw
/// frames this exposes into an unread count.
class ChatRemoteDataSource {
  ChatRemoteDataSource({
    TokenStorage? tokenStorage,
    WebSocketChannelFactory? channelFactory,
  })  : _tokenStorage = tokenStorage ?? TokenStorage.instance,
        _channelFactory = channelFactory ?? WebSocketChannel.connect;

  final TokenStorage _tokenStorage;
  final WebSocketChannelFactory _channelFactory;

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
