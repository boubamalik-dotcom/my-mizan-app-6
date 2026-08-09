import '../../../shared/exceptions/app_exception.dart';

/// Thrown when the Chat WebSocket cannot be established.
///
/// Distinct from `NetworkException`, which models *HTTP* failures with
/// a status code: a WebSocket handshake that the backend refuses
/// (`WS_1008_POLICY_VIOLATION` for a missing/expired/mismatched token)
/// surfaces to a Dart client as a socket-level failure, not a response
/// with a code to inspect. [message] is already display-ready Arabic.
class ChatConnectionException extends AppException {
  const ChatConnectionException(super.message, {this.cause});

  /// The underlying socket/platform error, kept for logging only —
  /// never shown to the user.
  final Object? cause;
}
