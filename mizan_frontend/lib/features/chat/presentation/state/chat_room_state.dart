import '../../data/chat_message.dart';

/// The Chat Room screen's state.
///
/// A separate hierarchy from `ChatState`, which models the *connection*
/// for the dashboard badge. This one models a *conversation*: its
/// history load and the messages in it. Both are `sealed`, like
/// `WalletState`, so every `switch` is checked for exhaustiveness.
sealed class ChatRoomState {
  const ChatRoomState();
}

/// The history request is in flight (which includes resolving the
/// caller's identity and, if needed, opening the socket first).
class ChatRoomLoading extends ChatRoomState {
  const ChatRoomLoading();
}

/// History loaded; [messages] is oldest-first and grows as new messages
/// arrive over the socket.
///
/// An empty [messages] list is a legitimate loaded state — a room nobody
/// has written in yet — and is what the screen's "لا توجد رسائل بعد"
/// placeholder renders from.
class ChatRoomReady extends ChatRoomState {
  const ChatRoomReady({
    required this.messages,
    required this.viewerId,
    this.isConnected = true,
  });

  final List<ChatMessage> messages;

  /// The signed-in user's chat identity (their email), so the UI can
  /// tell their own messages from everyone else's.
  final String viewerId;

  /// Whether the socket is open. When false the composer is disabled,
  /// because a sent message would be dropped rather than delivered.
  final bool isConnected;

  bool get isEmpty => messages.isEmpty;

  ChatRoomReady copyWith({List<ChatMessage>? messages, bool? isConnected}) {
    return ChatRoomReady(
      messages: messages ?? this.messages,
      viewerId: viewerId,
      isConnected: isConnected ?? this.isConnected,
    );
  }
}

/// The history could not be loaded. [message] is display-ready Arabic.
class ChatRoomError extends ChatRoomState {
  const ChatRoomError(this.message);

  final String message;
}
