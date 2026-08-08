import 'package:flutter/material.dart';

import '../../../../shared/design_system/constants/app_constants.dart';
import '../../../../shared/design_system/theme/color_scheme.dart';

/// The message input pinned to the bottom of the chat room.
///
/// Owns its own [TextEditingController] so the field can be cleared the
/// instant a message is handed off, and tracks whether there is anything
/// to send so the send button is only live when it would do something.
class ChatComposer extends StatefulWidget {
  const ChatComposer({
    super.key,
    required this.onSend,
    this.enabled = true,
  });

  /// Called with the trimmed message text. The field is cleared before
  /// this runs, so a slow send never leaves the user's text sitting
  /// there looking unsent.
  final void Function(String content) onSend;

  /// False while the socket is closed — a message sent then would be
  /// dropped rather than delivered.
  final bool enabled;

  @override
  State<ChatComposer> createState() => _ChatComposerState();
}

class _ChatComposerState extends State<ChatComposer> {
  final TextEditingController _controller = TextEditingController();
  final FocusNode _focusNode = FocusNode();
  bool _canSend = false;

  @override
  void initState() {
    super.initState();
    _controller.addListener(_syncCanSend);
  }

  @override
  void dispose() {
    _controller.removeListener(_syncCanSend);
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _syncCanSend() {
    final bool canSend = _controller.text.trim().isNotEmpty;
    if (canSend != _canSend) setState(() => _canSend = canSend);
  }

  void _submit() {
    final String content = _controller.text.trim();
    if (content.isEmpty || !widget.enabled) return;

    // Cleared first, so the field is empty the moment the user hits
    // send regardless of how long the send itself takes.
    _controller.clear();
    widget.onSend(content);
    _focusNode.requestFocus();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: MizanColors.surface,
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: MizanColors.navy.withOpacity(0.06),
            blurRadius: 12,
            offset: const Offset(0, -3),
          ),
        ],
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.md,
            AppSpacing.sm,
            AppSpacing.md,
            AppSpacing.sm,
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: <Widget>[
              Expanded(
                child: TextField(
                  controller: _controller,
                  focusNode: _focusNode,
                  enabled: widget.enabled,
                  minLines: 1,
                  maxLines: 4,
                  textInputAction: TextInputAction.send,
                  onSubmitted: (_) => _submit(),
                  decoration: InputDecoration(
                    hintText: widget.enabled
                        ? 'اكتب رسالتك…'
                        : 'الاتصال بخدمة الدردشة منقطع',
                    filled: true,
                    fillColor: MizanColors.background,
                    contentPadding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.md,
                      vertical: AppSpacing.sm + 2,
                    ),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(AppRadius.card * 1.5),
                      borderSide: BorderSide.none,
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(AppRadius.card * 1.5),
                      borderSide: BorderSide.none,
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(AppRadius.card * 1.5),
                      borderSide: const BorderSide(color: MizanColors.gold),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              _SendButton(
                enabled: widget.enabled && _canSend,
                onPressed: _submit,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SendButton extends StatelessWidget {
  const _SendButton({required this.enabled, required this.onPressed});

  final bool enabled;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: enabled ? MizanColors.gold : MizanColors.background,
      shape: const CircleBorder(),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: enabled ? onPressed : null,
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.sm + 2),
          child: Icon(
            // Mirrored automatically under RTL, so the plane always
            // points the way the message is going.
            Icons.send_rounded,
            semanticLabel: 'إرسال',
            size: 22,
            color: enabled ? Colors.white : MizanColors.textSecondary,
          ),
        ),
      ),
    );
  }
}
