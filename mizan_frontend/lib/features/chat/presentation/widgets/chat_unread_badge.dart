import 'package:flutter/material.dart';

import '../../../../shared/design_system/theme/color_scheme.dart';
import '../state/chat_state.dart';

/// Maps a [ChatState] to the small badge overlaid on the Chat half's
/// icon in the dashboard's Fulcrum Card.
///
/// Deliberately one of only two widgets wrapped in a
/// `BlocBuilder<ChatCubit, ChatState>` (the other being
/// [ChatStatusText]), so a chat state change repaints just the badge
/// and its status line — never the wallet half, the icons, or anything
/// else on the card.
///
/// Renders:
///
///  * [ChatConnecting] — a miniature gold progress indicator;
///  * [ChatConnected] — a gold circle with the white unread count,
///    or nothing at all when there is nothing unread;
///  * [ChatDisconnected]/[ChatError] — a subtle grey outlined
///    offline marker.
class ChatUnreadBadge extends StatelessWidget {
  const ChatUnreadBadge({super.key, required this.state});

  final ChatState state;

  @override
  Widget build(BuildContext context) {
    return switch (state) {
      ChatConnecting() => const SizedBox(
          height: 14,
          width: 14,
          child: CircularProgressIndicator(
            strokeWidth: 1.8,
            valueColor: AlwaysStoppedAnimation<Color>(MizanColors.gold),
          ),
        ),
      ChatConnected(:final unreadCount) => unreadCount > 0
          ? _UnreadCountBadge(unreadCount: unreadCount)
          : const SizedBox.shrink(),
      ChatDisconnected() || ChatError() => const _OfflineBadge(),
    };
  }
}

/// A gold circle with the white unread count — capped at `9+` so a
/// busy inbox can never widen the badge unboundedly.
class _UnreadCountBadge extends StatelessWidget {
  const _UnreadCountBadge({required this.unreadCount});

  final int unreadCount;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
      constraints: const BoxConstraints(minWidth: 18),
      decoration: BoxDecoration(
        color: MizanColors.gold,
        borderRadius: BorderRadius.circular(9),
        border: Border.all(color: Colors.white, width: 1.5),
      ),
      child: Text(
        unreadCount > 9 ? '9+' : '$unreadCount',
        textAlign: TextAlign.center,
        textDirection: TextDirection.ltr,
        style: const TextStyle(
          color: Colors.white,
          fontSize: 10,
          fontWeight: FontWeight.w700,
          height: 1.3,
        ),
      ),
    );
  }
}

/// A muted, outlined marker for a chat service that is not currently
/// reachable — deliberately quiet (no red, no fill) since being
/// offline is a status, not an error the user must act on.
class _OfflineBadge extends StatelessWidget {
  const _OfflineBadge();

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 18,
      width: 18,
      decoration: BoxDecoration(
        color: MizanColors.navy.withOpacity(0.35),
        shape: BoxShape.circle,
        border: Border.all(color: Colors.white54, width: 1.2),
      ),
      child: const Icon(
        Icons.cloud_off_rounded,
        size: 10,
        color: Colors.white70,
      ),
    );
  }
}
