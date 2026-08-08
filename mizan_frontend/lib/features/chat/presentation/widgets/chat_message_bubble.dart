import 'package:flutter/material.dart';
import 'package:intl/intl.dart' show DateFormat;

import '../../../../shared/design_system/constants/app_constants.dart';
import '../../../../shared/design_system/theme/color_scheme.dart';
import '../../data/chat_message.dart';

/// One message in the conversation.
///
/// Outgoing messages are gold with white text and sit at the *end* of
/// the row; incoming ones are white with navy text at the *start*. Both
/// use directional alignment and `BorderRadiusDirectional`, so the whole
/// layout mirrors correctly under the app's RTL locale — the tail lands
/// on the side the message came from without any manual left/right
/// branching.
class ChatMessageBubble extends StatelessWidget {
  const ChatMessageBubble({
    super.key,
    required this.message,
    required this.isMine,
    this.showSender = false,
  });

  final ChatMessage message;
  final bool isMine;

  /// Whether to label the message with its author — worth showing in a
  /// shared room, but only on the first of a run from the same person.
  final bool showSender;

  static final DateFormat _timeFormat = DateFormat.Hm();

  @override
  Widget build(BuildContext context) {
    final Color background = isMine ? MizanColors.gold : MizanColors.surface;
    final Color foreground = isMine ? Colors.white : MizanColors.navy;

    return Align(
      alignment: isMine
          ? AlignmentDirectional.centerEnd
          : AlignmentDirectional.centerStart,
      child: ConstrainedBox(
        // Keeps a long message from spanning the full width, which is
        // what makes the two sides readable as a conversation.
        constraints: BoxConstraints(
          maxWidth: MediaQuery.sizeOf(context).width * 0.78,
        ),
        child: Container(
          margin: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md,
            vertical: AppSpacing.sm,
          ),
          decoration: BoxDecoration(
            color: background,
            borderRadius: BorderRadiusDirectional.only(
              topStart: const Radius.circular(AppRadius.card),
              topEnd: const Radius.circular(AppRadius.card),
              bottomStart: Radius.circular(isMine ? AppRadius.card : 4),
              bottomEnd: Radius.circular(isMine ? 4 : AppRadius.card),
            ).resolve(Directionality.of(context)),
            boxShadow: <BoxShadow>[
              BoxShadow(
                color: MizanColors.navy.withOpacity(isMine ? 0.18 : 0.07),
                blurRadius: 8,
                offset: const Offset(0, 3),
              ),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              if (showSender && !isMine) ...<Widget>[
                Text(
                  message.senderId,
                  textDirection: TextDirection.ltr,
                  style: const TextStyle(
                    color: MizanColors.textSecondary,
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 2),
              ],
              Text(
                message.content,
                style: TextStyle(
                  color: foreground,
                  fontSize: 15,
                  height: 1.35,
                ),
              ),
              const SizedBox(height: 2),
              Align(
                alignment: AlignmentDirectional.centerEnd,
                child: Text(
                  _timeFormat.format(message.createdAt),
                  textDirection: TextDirection.ltr,
                  style: TextStyle(
                    color: isMine
                        ? Colors.white.withOpacity(0.85)
                        : MizanColors.textSecondary,
                    fontSize: 10,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
