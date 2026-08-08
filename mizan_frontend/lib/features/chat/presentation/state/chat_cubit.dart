import 'dart:async';

import 'package:flutter_bloc/flutter_bloc.dart';

import '../../../../shared/exceptions/app_exception.dart';
import '../../../auth/data/auth_repository.dart';
import '../../../auth/domain/entities/auth_user.dart';
import '../../data/chat_repository.dart';
import 'chat_state.dart';

/// Drives the Chat half of the dashboard's Fulcrum Card.
///
/// A [Cubit] rather than a full `Bloc`, matching `WalletCubit`: the
/// feature's only inputs today are "connect" and "mark read", so there
/// is no event stream worth naming separately from the methods that
/// trigger them.
///
/// `HostDashboardPage` creates one per dashboard visit via
/// `BlocProvider` and calls [initializeChat] immediately, alongside
/// the wallet's own load. Only the two small
/// `BlocBuilder<ChatCubit, ChatState>`s around the chat badge and its
/// status line ever rebuild when this emits — never the wallet half or
/// the rest of the dashboard.
class ChatCubit extends Cubit<ChatState> {
  ChatCubit({ChatRepository? chatRepository, AuthRepository? authRepository})
      : _chatRepository = chatRepository ?? ChatRepository.instance,
        _authRepository = authRepository ?? AuthRepository.instance,
        super(const ChatDisconnected());

  final ChatRepository _chatRepository;
  final AuthRepository _authRepository;

  StreamSubscription<int>? _unreadSubscription;

  /// Resolves the authenticated user's identity, then opens the chat
  /// socket as that identity.
  ///
  /// `client_id` must be the user's **email**, not their id: the
  /// backend authorizes the socket by comparing it against the JWT's
  /// subject, which `AuthController.login` sets to the email. So this
  /// asks `AuthRepository.getCurrentUser()` for the profile first
  /// rather than guessing.
  ///
  /// Safe to call again to retry after a [ChatError] or
  /// [ChatDisconnected] — `ChatRepository.connect` tears any previous
  /// connection down first.
  Future<void> initializeChat() async {
    emit(const ChatConnecting());

    try {
      final AuthUser user = await _authRepository.getCurrentUser();
      final Stream<int> unreadCounts =
          await _chatRepository.connect(clientId: user.email);

      if (isClosed) {
        // The dashboard was disposed mid-handshake; drop the socket
        // we just opened rather than leaking it.
        await _chatRepository.disconnect();
        return;
      }

      emit(const ChatConnected());

      await _unreadSubscription?.cancel();
      _unreadSubscription = unreadCounts.listen(
        (int unreadCount) {
          if (!isClosed) emit(ChatConnected(unreadCount: unreadCount));
        },
        onError: (Object _) {
          if (!isClosed) {
            emit(const ChatError('انقطع الاتصال بخدمة الدردشة.'));
          }
        },
        onDone: () {
          if (!isClosed) emit(const ChatDisconnected());
        },
        cancelOnError: false,
      );
    } on AppException catch (error) {
      if (!isClosed) emit(ChatError(error.message));
    } catch (_) {
      if (!isClosed) {
        emit(const ChatError('حدث خطأ غير متوقع في خدمة الدردشة.'));
      }
    }
  }

  /// Clears the unread badge (e.g. once the user opens the chat
  /// screen). No-op unless currently connected.
  void markAllAsRead() {
    if (state is! ChatConnected) return;
    _chatRepository.markAllAsRead();
    if (!isClosed) emit(const ChatConnected());
  }

  /// Cancels the unread subscription and closes the socket.
  ///
  /// `BlocProvider` calls this when the dashboard is disposed — which
  /// includes logging out and the `AuthInterceptor`'s forced 401
  /// redirect, both of which replace the whole navigation stack — so
  /// an authenticated socket never outlives the session that
  /// authorized it. (Outright app termination tears the socket down
  /// with the process; there is no Dart callback guaranteed to run
  /// first, so nothing further is needed there.)
  @override
  Future<void> close() async {
    await _unreadSubscription?.cancel();
    _unreadSubscription = null;
    await _chatRepository.disconnect();
    return super.close();
  }
}
