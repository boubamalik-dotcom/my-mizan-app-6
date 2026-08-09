import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../../../shared/design_system/constants/app_constants.dart';
import '../../../../shared/design_system/theme/color_scheme.dart';
import '../../../../shared/exceptions/app_exception.dart';
import '../../data/chat_message.dart';
import '../state/chat_room_cubit.dart';
import '../state/chat_room_state.dart';
import '../widgets/chat_composer.dart';
import '../widgets/chat_message_bubble.dart';

/// "الدردشة الآمنة" — the conversation view, reached by tapping the chat
/// half of the dashboard's Fulcrum Card.
///
/// Runs its own [ChatRoomCubit] for the history and message list, but
/// shares the app-wide `ChatRepository` socket the dashboard already
/// opened, so entering the room neither reconnects nor disturbs the
/// unread badge (it clears it, which is the point).
class ChatRoomPage extends StatelessWidget {
  const ChatRoomPage({super.key, ChatRoomCubit? chatRoomCubit})
      : _cubitOverride = chatRoomCubit;

  /// Injectable for tests, which must not open a socket or hit the
  /// network. In production a fresh cubit is created and immediately
  /// told to [ChatRoomCubit.loadRoom].
  final ChatRoomCubit? _cubitOverride;

  @override
  Widget build(BuildContext context) {
    return BlocProvider<ChatRoomCubit>(
      create: (_) => (_cubitOverride ?? ChatRoomCubit())..loadRoom(),
      child: Builder(
        builder: (BuildContext context) => Scaffold(
          backgroundColor: MizanColors.background,
          appBar: AppBar(
            title: const Text('الدردشة الآمنة'),
            leading: IconButton(
              // Points forward in reading order, which under RTL is the
              // correct "back" direction.
              icon: const Icon(Icons.arrow_forward_rounded),
              tooltip: 'رجوع',
              onPressed: () => Navigator.of(context).pop(),
            ),
          ),
          body: Column(
            children: <Widget>[
              Expanded(
                child: BlocBuilder<ChatRoomCubit, ChatRoomState>(
                  builder: (BuildContext context, ChatRoomState state) {
                    return switch (state) {
                      ChatRoomLoading() => const _CenteredProgress(),
                      ChatRoomError(:final message) =>
                        _LoadFailure(message: message),
                      ChatRoomReady(isEmpty: true) => const _EmptyRoom(),
                      ChatRoomReady() => _MessageList(state: state),
                    };
                  },
                ),
              ),
              BlocBuilder<ChatRoomCubit, ChatRoomState>(
                // Scoped to the composer: it only cares whether the room
                // is loaded and the socket is up, not about each new
                // message arriving.
                buildWhen: (ChatRoomState previous, ChatRoomState current) =>
                    _composerEnabled(previous) != _composerEnabled(current),
                builder: (BuildContext context, ChatRoomState state) {
                  return ChatComposer(
                    enabled: _composerEnabled(state),
                    onSend: (String content) => _send(context, content),
                  );
                },
              ),
            ],
          ),
        ),
      ),
    );
  }

  static bool _composerEnabled(ChatRoomState state) =>
      state is ChatRoomReady && state.isConnected;

  /// Hands the message to the cubit, surfacing the rare failure (a
  /// socket that dropped between the last rebuild and this tap) rather
  /// than letting the message vanish silently.
  static void _send(BuildContext context, String content) {
    try {
      context.read<ChatRoomCubit>().sendMessage(content);
    } on AppException catch (error) {
      _showError(context, error.message);
    } catch (_) {
      _showError(context, 'تعذّر إرسال الرسالة. يرجى المحاولة مرة أخرى.');
    }
  }

  static void _showError(BuildContext context, String message) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(content: Text(message), backgroundColor: MizanColors.error),
      );
  }
}

class _MessageList extends StatelessWidget {
  const _MessageList({required this.state});

  final ChatRoomReady state;

  @override
  Widget build(BuildContext context) {
    final List<ChatMessage> messages = state.messages;

    return ListView.builder(
      // Anchored at the bottom, the chat convention: index 0 is the
      // newest message, so an arriving message appears in view without
      // any scroll-to-end bookkeeping, and a partially-scrolled-up
      // history stays put.
      reverse: true,
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.md,
      ),
      itemCount: messages.length,
      itemBuilder: (BuildContext context, int index) {
        // The list itself is oldest-first (the order the backend returns
        // and the order messages are appended in), so a reversed view
        // indexes from the end.
        final int messageIndex = messages.length - 1 - index;
        final ChatMessage message = messages[messageIndex];
        final ChatMessage? previous =
            messageIndex > 0 ? messages[messageIndex - 1] : null;

        return ChatMessageBubble(
          message: message,
          isMine: message.isMine(state.viewerId),
          // Only label the first message of a run from the same author.
          showSender: previous?.senderId != message.senderId,
        );
      },
    );
  }
}

class _CenteredProgress extends StatelessWidget {
  const _CenteredProgress();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: CircularProgressIndicator(
        valueColor: AlwaysStoppedAnimation<Color>(MizanColors.gold),
      ),
    );
  }
}

class _EmptyRoom extends StatelessWidget {
  const _EmptyRoom();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            CircleAvatar(
              radius: 32,
              backgroundColor: MizanColors.gold.withOpacity(0.14),
              child: const Icon(
                Icons.forum_outlined,
                color: MizanColors.gold,
                size: 30,
              ),
            ),
            const SizedBox(height: AppSpacing.md),
            Text(
              'لا توجد رسائل بعد',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(
              'ابدأ المحادثة بإرسال أول رسالة.',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}

class _LoadFailure extends StatelessWidget {
  const _LoadFailure({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            const Icon(
              Icons.error_outline_rounded,
              color: MizanColors.error,
              size: 32,
            ),
            const SizedBox(height: AppSpacing.md),
            Text(
              message,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: AppSpacing.md),
            FilledButton.icon(
              onPressed: () => context.read<ChatRoomCubit>().loadRoom(),
              icon: const Icon(Icons.refresh_rounded, size: 18),
              label: const Text('إعادة المحاولة'),
            ),
          ],
        ),
      ),
    );
  }
}
