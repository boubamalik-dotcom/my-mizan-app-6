import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/features/auth/data/auth_repository.dart';
import 'package:mizan_frontend/features/auth/domain/entities/auth_user.dart';
import 'package:mizan_frontend/features/chat/data/chat_exceptions.dart';
import 'package:mizan_frontend/features/chat/data/chat_repository.dart';
import 'package:mizan_frontend/features/chat/presentation/state/chat_cubit.dart';
import 'package:mizan_frontend/features/chat/presentation/state/chat_state.dart';
import 'package:mizan_frontend/shared/exceptions/network_exception.dart';
import 'package:mocktail/mocktail.dart';

class MockChatRepository extends Mock implements ChatRepository {}

class MockAuthRepository extends Mock implements AuthRepository {}

const AuthUser _testUser = AuthUser(
  id: 'user-1',
  email: 'alice@example.com',
  fullName: 'Alice Example',
  isActive: true,
);

void main() {
  late MockChatRepository chatRepository;
  late MockAuthRepository authRepository;
  late StreamController<int> unreadCounts;
  late ChatCubit cubit;

  setUp(() {
    chatRepository = MockChatRepository();
    authRepository = MockAuthRepository();
    unreadCounts = StreamController<int>.broadcast();

    when(() => authRepository.getCurrentUser())
        .thenAnswer((_) async => _testUser);
    when(() => chatRepository.connect(
          clientId: any(named: 'clientId'),
          roomId: any(named: 'roomId'),
        )).thenAnswer((_) async => unreadCounts.stream);
    when(() => chatRepository.disconnect()).thenAnswer((_) async {});
    when(() => chatRepository.markAllAsRead()).thenReturn(null);

    cubit = ChatCubit(
      chatRepository: chatRepository,
      authRepository: authRepository,
    );
  });

  tearDown(() async {
    await cubit.close();
    if (!unreadCounts.isClosed) await unreadCounts.close();
  });

  test('starts disconnected', () {
    expect(cubit.state, isA<ChatDisconnected>());
  });

  test(
      'initializeChat connects as the user\'s email into the room named '
      'after their id', () async {
    // Two different identifiers on purpose: the backend authorizes the
    // client id against the JWT subject (the email), and scopes the room
    // by user id (which cannot change under the user the way an email
    // can).
    await cubit.initializeChat();

    verify(() => chatRepository.connect(
          clientId: 'alice@example.com',
          roomId: 'private_user-1',
        )).called(1);
  });

  test('initializeChat never connects to a shared room', () async {
    // The vulnerability this replaced: every client joined `general`,
    // and because history is scoped per room, that made every user's
    // messages readable by every other user. A regression here would
    // reopen it, so it is asserted directly rather than only implied by
    // the positive case above.
    await cubit.initializeChat();

    final String room = verify(() => chatRepository.connect(
          clientId: any(named: 'clientId'),
          roomId: captureAny(named: 'roomId'),
        )).captured.single as String;

    expect(room, 'private_user-1');
    expect(room, isNot('general'));
    expect(room, contains(_testUser.id));
  });

  test('a different user gets a different room', () async {
    // Nothing about the room is global: it is a function of who is
    // signed in.
    when(() => authRepository.getCurrentUser()).thenAnswer(
      (_) async => const AuthUser(
        id: 'user-2',
        email: 'bob@example.com',
        fullName: 'Bob',
        isActive: true,
      ),
    );

    await cubit.initializeChat();

    verify(() => chatRepository.connect(
          clientId: 'bob@example.com',
          roomId: 'private_user-2',
        )).called(1);
  });

  test('initializeChat emits [ChatConnecting, ChatConnected] on success',
      () async {
    final List<ChatState> emitted = <ChatState>[];
    final Future<void> collect = cubit.stream.forEach(emitted.add);

    await cubit.initializeChat();
    await cubit.close();
    await collect;

    expect(emitted, <Matcher>[
      isA<ChatConnecting>(),
      isA<ChatConnected>().having(
        (ChatState s) => (s as ChatConnected).unreadCount,
        'unreadCount',
        0,
      ),
    ]);
  });

  test('an incoming unread count re-emits ChatConnected with that count',
      () async {
    await cubit.initializeChat();

    unreadCounts.add(2);
    await Future<void>.delayed(Duration.zero);

    expect(cubit.state, isA<ChatConnected>());
    expect((cubit.state as ChatConnected).unreadCount, 2);
  });

  test('the socket closing emits ChatDisconnected', () async {
    await cubit.initializeChat();

    await unreadCounts.close();
    await Future<void>.delayed(Duration.zero);

    expect(cubit.state, isA<ChatDisconnected>());
  });

  test('a socket error emits ChatError', () async {
    await cubit.initializeChat();

    unreadCounts.addError(StateError('socket died'));
    await Future<void>.delayed(Duration.zero);

    expect(cubit.state, isA<ChatError>());
  });

  test('a ChatConnectionException surfaces its own Arabic message', () async {
    when(() => chatRepository.connect(
          clientId: any(named: 'clientId'),
          roomId: any(named: 'roomId'),
        )).thenThrow(const ChatConnectionException('يجب تسجيل الدخول أولاً.'));

    await cubit.initializeChat();

    expect(cubit.state, isA<ChatError>());
    expect((cubit.state as ChatError).message, 'يجب تسجيل الدخول أولاً.');
  });

  test('a failure resolving the current user also emits ChatError', () async {
    when(() => authRepository.getCurrentUser())
        .thenThrow(const NetworkException('انتهت صلاحية الجلسة.'));

    await cubit.initializeChat();

    expect(cubit.state, isA<ChatError>());
    expect((cubit.state as ChatError).message, 'انتهت صلاحية الجلسة.');
  });

  test('an unexpected error falls back to a generic Arabic message', () async {
    when(() => chatRepository.connect(
          clientId: any(named: 'clientId'),
          roomId: any(named: 'roomId'),
        )).thenThrow(StateError('boom'));

    await cubit.initializeChat();

    expect(cubit.state, isA<ChatError>());
    expect(
      (cubit.state as ChatError).message,
      'حدث خطأ غير متوقع في خدمة الدردشة.',
    );
  });

  test('markAllAsRead clears the badge while connected', () async {
    await cubit.initializeChat();
    unreadCounts.add(5);
    await Future<void>.delayed(Duration.zero);
    expect((cubit.state as ChatConnected).unreadCount, 5);

    cubit.markAllAsRead();

    verify(() => chatRepository.markAllAsRead()).called(1);
    expect((cubit.state as ChatConnected).unreadCount, 0);
  });

  test('markAllAsRead is a no-op when not connected', () {
    cubit.markAllAsRead();

    verifyNever(() => chatRepository.markAllAsRead());
    expect(cubit.state, isA<ChatDisconnected>());
  });

  test('close() disconnects the socket so it never outlives the session',
      () async {
    await cubit.initializeChat();

    await cubit.close();

    verify(() => chatRepository.disconnect()).called(greaterThanOrEqualTo(1));
  });

  test('initializeChat can be called again to retry after an error', () async {
    when(() => chatRepository.connect(
          clientId: any(named: 'clientId'),
          roomId: any(named: 'roomId'),
        )).thenThrow(const ChatConnectionException('تعذّر الاتصال.'));
    await cubit.initializeChat();
    expect(cubit.state, isA<ChatError>());

    when(() => chatRepository.connect(
          clientId: any(named: 'clientId'),
          roomId: any(named: 'roomId'),
        )).thenAnswer((_) async => unreadCounts.stream);
    await cubit.initializeChat();

    expect(cubit.state, isA<ChatConnected>());
  });
}
