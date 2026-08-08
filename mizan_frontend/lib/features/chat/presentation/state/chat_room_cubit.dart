import 'dart:async';

import 'package:flutter_bloc/flutter_bloc.dart';

import '../../../../shared/exceptions/app_exception.dart';
import '../../../auth/data/auth_repository.dart';
import '../../../auth/domain/entities/auth_user.dart';
import '../../data/chat_message.dart';
import '../../data/chat_repository.dart';
import 'chat_room_state.dart';

/// Drives `ChatRoomPage`: loads a room's history, then keeps it current
/// from the live socket.
///
/// Deliberately separate from `ChatCubit`, which owns the *connection*
/// for the dashboard badge and outlives this screen. The division of
/// responsibility matters: this cubit never opens or closes a socket
/// that the dashboard is using — see [close].
class ChatRoomCubit extends Cubit<ChatRoomState> {
  ChatRoomCubit({
    ChatRepository? chatRepository,
    AuthRepository? authRepository,
    this.roomId = kDefaultChatRoomId,
  })  : _chatRepository = chatRepository ?? ChatRepository.instance,
        _authRepository = authRepository ?? AuthRepository.instance,
        super(const ChatRoomLoading());

  final ChatRepository _chatRepository;
  final AuthRepository _authRepository;
  final String roomId;

  StreamSubscription<ChatMessage>? _messageSubscription;

  /// Loads the room: resolves the caller, ensures a socket is open,
  /// fetches history, starts appending live messages, and clears the
  /// unread badge.
  ///
  /// Safe to call again to retry after a [ChatRoomError].
  Future<void> loadRoom() async {
    emit(const ChatRoomLoading());

    try {
      final AuthUser user = await _authRepository.getCurrentUser();

      // The dashboard normally has the socket open already. Only
      // connect when it does not — reconnecting would replace the
      // streams its `ChatCubit` listens to and darken its badge.
      if (!_chatRepository.isConnected) {
        await _chatRepository.connect(clientId: user.email);
      }

      final List<ChatMessage> history = await _chatRepository.fetchHistory(
        clientId: user.email,
        roomId: roomId,
      );
      if (isClosed) return;

      emit(
        ChatRoomReady(
          messages: _conversationalOnly(history),
          viewerId: user.email,
          isConnected: _chatRepository.isConnected,
        ),
      );

      _listenForMessages();

      // Opening the room is what marks the conversation read; this
      // publishes 0 on the repository's unread stream, so the
      // dashboard's badge clears without this cubit touching it.
      _chatRepository.markAllAsRead();
    } on AppException catch (error) {
      if (!isClosed) emit(ChatRoomError(error.message));
    } catch (_) {
      if (!isClosed) {
        emit(const ChatRoomError(
            'تعذّر تحميل المحادثة. يرجى المحاولة مرة أخرى.'));
      }
    }
  }

  /// Sends [content] to the room.
  ///
  /// Returns without doing anything for blank input. The sent message is
  /// **not** added locally: the backend relays it back to its author, so
  /// it arrives through the same stream as everyone else's (see
  /// `ChatRepository.sendMessage`), which also means what is on screen
  /// is exactly what was persisted.
  ///
  /// Throws an [AppException] if the socket is closed, for the composer
  /// to surface — a message must never look sent when it was not.
  void sendMessage(String content) {
    if (content.trim().isEmpty) return;
    _chatRepository.sendMessage(content);
  }

  void _listenForMessages() {
    _messageSubscription?.cancel();
    _messageSubscription = _chatRepository.incomingMessages.listen(
      (ChatMessage message) {
        if (isClosed) return;
        final ChatRoomState current = state;
        if (current is! ChatRoomReady) return;
        if (message.roomId != roomId) return;
        if (!message.isConversational) return;
        // The same message can arrive twice when a history fetch races
        // the socket; identity is the server-assigned id.
        if (current.messages.contains(message)) return;

        emit(
          current.copyWith(
            messages: <ChatMessage>[...current.messages, message],
          ),
        );
      },
      onError: (Object _) {
        // Connection-level failures are already surfaced by the
        // dashboard's `ChatCubit`; here it only means no more messages
        // will arrive, so disable the composer rather than throwing the
        // loaded conversation away.
        _markDisconnected();
      },
      onDone: _markDisconnected,
      cancelOnError: false,
    );
  }

  void _markDisconnected() {
    if (isClosed) return;
    final ChatRoomState current = state;
    if (current is ChatRoomReady) {
      emit(current.copyWith(isConnected: false));
    }
  }

  /// Join/leave notices are dropped from the conversation.
  ///
  /// They are real messages in the backend's history, but their content
  /// is server-generated English (`"x@y.com" joined the room.`), which
  /// would read as broken copy in this Arabic UI. The unread counter
  /// already ignores them, so this keeps the two consistent.
  List<ChatMessage> _conversationalOnly(List<ChatMessage> messages) {
    return messages
        .where((ChatMessage message) => message.isConversational)
        .toList();
  }

  /// Cancels only this screen's subscription.
  ///
  /// Critically does **not** disconnect: the socket belongs to the
  /// dashboard's `ChatCubit`, which is still mounted beneath this route.
  /// Closing it here would kill the unread badge the moment the user
  /// backed out of the room.
  @override
  Future<void> close() async {
    await _messageSubscription?.cancel();
    _messageSubscription = null;
    return super.close();
  }
}
