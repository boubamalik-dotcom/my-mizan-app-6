import 'package:flutter/material.dart';

import '../state/chat_state.dart';

/// The one-line status shown beneath the "الدردشة الآمنة" label on the
/// dashboard's Fulcrum Card, describing the live connection in words
/// rather than leaving the badge alone to imply it.
///
/// Paired with [ChatUnreadBadge]: both are wrapped in their own small
/// `BlocBuilder<ChatCubit, ChatState>` by `HostDashboardPage`, so a
/// chat state change rebuilds only these two little widgets.
class ChatStatusText extends StatelessWidget {
  const ChatStatusText({super.key, required this.state});

  final ChatState state;

  @override
  Widget build(BuildContext context) {
    final String label = switch (state) {
      ChatConnecting() => 'جارٍ الاتصال…',
      ChatConnected(:final unreadCount) =>
        unreadCount > 0 ? 'لديك رسائل غير مقروءة' : 'محادثات مشفّرة بالكامل',
      ChatDisconnected() => 'غير متصل حاليًا',
      ChatError() => 'تعذّر الاتصال',
    };

    return Text(
      label,
      textAlign: TextAlign.center,
      style: const TextStyle(color: Colors.white70, fontSize: 12),
    );
  }
}
