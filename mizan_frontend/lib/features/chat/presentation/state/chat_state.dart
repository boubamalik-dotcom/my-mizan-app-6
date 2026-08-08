/// The Chat engine's connection state, driving the badge and status
/// line on the Chat half of the dashboard's Fulcrum Card.
///
/// Modeled as a `sealed` hierarchy — like `WalletState` — so every
/// `switch` over it is checked for exhaustiveness by the compiler.
sealed class ChatState {
  const ChatState();
}

/// The socket handshake is in flight (also the state while the
/// authenticated user's identity is being resolved, since that is a
/// prerequisite of connecting).
class ChatConnecting extends ChatState {
  const ChatConnecting();
}

/// The socket is open. [unreadCount] is the number of messages
/// received from other participants since connecting (or since the
/// last `ChatCubit.markAllAsRead`).
class ChatConnected extends ChatState {
  const ChatConnected({this.unreadCount = 0});

  final int unreadCount;
}

/// No socket is open — either because one has not been attempted yet
/// (the initial state) or because a previously-open one closed
/// cleanly, e.g. on logout or a server-side shutdown.
class ChatDisconnected extends ChatState {
  const ChatDisconnected();
}

/// The connection failed or dropped with an error. [message] is
/// already display-ready Arabic (see `ChatConnectionException`).
class ChatError extends ChatState {
  const ChatError(this.message);

  final String message;
}
