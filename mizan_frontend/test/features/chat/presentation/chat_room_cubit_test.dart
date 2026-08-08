import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/features/auth/data/auth_repository.dart';
import 'package:mizan_frontend/features/auth/domain/entities/auth_user.dart';
import 'package:mizan_frontend/features/chat/data/chat_message.dart';
import 'package:mizan_frontend/features/chat/data/chat_repository.dart';
import 'package:mizan_frontend/features/chat/presentation/state/chat_room_cubit.dart';
import 'package:mizan_frontend/features/chat/presentation/state/chat_room_state.dart';
import 'package:mizan_frontend/shared/exceptions/network_exception.dart';
import 'package:mocktail/mocktail.dart';

class MockChatRepository extends Mock implements ChatRepository {}

class MockAuthRepository extends Mock implements AuthRepository {}

const AuthUser _alice = AuthUser(
  id: 'user-1',
  email: 'alice@example.com',
  fullName: 'Alice',
  isActive: true,
);

ChatMessage _message({
  required String id,
  String senderId = 'bob@example.com',
  String content = 'مرحبا',
  String roomId = kDefaultChatRoomId,
  String type = 'text',
}) {
  return ChatMessage.fromJson(<String, dynamic>{
    'id': id,
    'room_id': roomId,
    'sender_id': senderId,
    'content': content,
    'type': type,
    'created_at': '2026-01-01T00:00:00Z',
  });
}

void main() {
  late MockChatRepository chatRepository;
  late MockAuthRepository authRepository;
  late StreamController<ChatMessage> incoming;
  late ChatRoomCubit cubit;

  setUp(() {
    chatRepository = MockChatRepository();
    authRepository = MockAuthRepository();
    incoming = StreamController<ChatMessage>.broadcast();

    when(() => authRepository.getCurrentUser()).thenAnswer((_) async => _alice);
    when(() => chatRepository.isConnected).thenReturn(true);
    when(() => chatRepository.incomingMessages)
        .thenAnswer((_) => incoming.stream);
    when(() => chatRepository.markAllAsRead()).thenReturn(null);
    when(
      () => chatRepository.fetchHistory(
        clientId: any(named: 'clientId'),
        roomId: any(named: 'roomId'),
        limit: any(named: 'limit'),
      ),
    ).thenAnswer((_) async => <ChatMessage>[]);

    cubit = ChatRoomCubit(
      chatRepository: chatRepository,
      authRepository: authRepository,
    );
  });

  tearDown(() async {
    await cubit.close();
    await incoming.close();
  });

  test('starts in ChatRoomLoading', () {
    expect(cubit.state, isA<ChatRoomLoading>());
  });

  group('loadRoom', () {
    test('fetches history for the signed-in user and exposes it oldest-first',
        () async {
      when(
        () => chatRepository.fetchHistory(
          clientId: any(named: 'clientId'),
          roomId: any(named: 'roomId'),
          limit: any(named: 'limit'),
        ),
      ).thenAnswer(
        (_) async => <ChatMessage>[_message(id: 'm1'), _message(id: 'm2')],
      );

      await cubit.loadRoom();

      final ChatRoomReady state = cubit.state as ChatRoomReady;
      expect(state.messages.map((ChatMessage m) => m.id), <String>['m1', 'm2']);
      expect(state.viewerId, 'alice@example.com');
      expect(state.isEmpty, isFalse);
      // The history endpoint authorizes on the caller's own email.
      verify(
        () => chatRepository.fetchHistory(
          clientId: 'alice@example.com',
          roomId: kDefaultChatRoomId,
        ),
      ).called(1);
    });

    test('an empty room is a loaded state, not an error', () async {
      await cubit.loadRoom();

      expect(cubit.state, isA<ChatRoomReady>());
      expect((cubit.state as ChatRoomReady).isEmpty, isTrue);
    });

    test('drops join/leave notices from the conversation', () async {
      when(
        () => chatRepository.fetchHistory(
          clientId: any(named: 'clientId'),
          roomId: any(named: 'roomId'),
          limit: any(named: 'limit'),
        ),
      ).thenAnswer(
        (_) async => <ChatMessage>[
          _message(id: 'join-1', type: 'join', content: 'bob joined'),
          _message(id: 'm1'),
          _message(id: 'leave-1', type: 'leave', content: 'bob left'),
        ],
      );

      await cubit.loadRoom();

      expect(
        (cubit.state as ChatRoomReady).messages.map((ChatMessage m) => m.id),
        <String>['m1'],
      );
    });

    test('reuses the socket the dashboard already opened', () async {
      when(() => chatRepository.isConnected).thenReturn(true);

      await cubit.loadRoom();

      // Reconnecting would replace the streams the dashboard's ChatCubit
      // listens to and darken its badge.
      verifyNever(
          () => chatRepository.connect(clientId: any(named: 'clientId')));
    });

    test('opens a socket when none is connected yet', () async {
      when(() => chatRepository.isConnected).thenReturn(false);
      when(() => chatRepository.connect(clientId: any(named: 'clientId')))
          .thenAnswer((_) async => const Stream<int>.empty());

      await cubit.loadRoom();

      verify(() => chatRepository.connect(clientId: 'alice@example.com'))
          .called(1);
    });

    test('clears the unread badge, since opening the room is reading it',
        () async {
      await cubit.loadRoom();

      verify(() => chatRepository.markAllAsRead()).called(1);
    });

    test('surfaces a history failure with its Arabic message', () async {
      when(
        () => chatRepository.fetchHistory(
          clientId: any(named: 'clientId'),
          roomId: any(named: 'roomId'),
          limit: any(named: 'limit'),
        ),
      ).thenThrow(const NetworkException('تعذّر الاتصال بالخادم.'));

      await cubit.loadRoom();

      expect(cubit.state, isA<ChatRoomError>());
      expect((cubit.state as ChatRoomError).message, 'تعذّر الاتصال بالخادم.');
    });

    test('falls back to a generic message for an unexpected failure', () async {
      when(() => authRepository.getCurrentUser()).thenThrow(StateError('boom'));

      await cubit.loadRoom();

      expect(cubit.state, isA<ChatRoomError>());
      expect(
        (cubit.state as ChatRoomError).message,
        contains('تعذّر تحميل المحادثة'),
      );
    });

    test('can retry after a failure and succeed', () async {
      when(
        () => chatRepository.fetchHistory(
          clientId: any(named: 'clientId'),
          roomId: any(named: 'roomId'),
          limit: any(named: 'limit'),
        ),
      ).thenThrow(const NetworkException('تعذّر الاتصال بالخادم.'));
      await cubit.loadRoom();
      expect(cubit.state, isA<ChatRoomError>());

      when(
        () => chatRepository.fetchHistory(
          clientId: any(named: 'clientId'),
          roomId: any(named: 'roomId'),
          limit: any(named: 'limit'),
        ),
      ).thenAnswer((_) async => <ChatMessage>[_message(id: 'm1')]);
      await cubit.loadRoom();

      expect(cubit.state, isA<ChatRoomReady>());
      expect((cubit.state as ChatRoomReady).messages, hasLength(1));
    });
  });

  group('live messages', () {
    test('appends an arriving message to the loaded list', () async {
      await cubit.loadRoom();

      incoming.add(_message(id: 'm1', content: 'أهلاً'));
      await Future<void>.delayed(Duration.zero);

      final ChatRoomReady state = cubit.state as ChatRoomReady;
      expect(state.messages.single.content, 'أهلاً');
    });

    test(
        "appends the user's own echoed message, which is how a sent "
        'message appears', () async {
      // `sendMessage` deliberately does not append locally: the backend
      // relays the author their own message back.
      await cubit.loadRoom();

      incoming.add(_message(id: 'mine', senderId: 'alice@example.com'));
      await Future<void>.delayed(Duration.zero);

      expect((cubit.state as ChatRoomReady).messages.single.id, 'mine');
    });

    test('de-duplicates a message already present from the history fetch',
        () async {
      when(
        () => chatRepository.fetchHistory(
          clientId: any(named: 'clientId'),
          roomId: any(named: 'roomId'),
          limit: any(named: 'limit'),
        ),
      ).thenAnswer((_) async => <ChatMessage>[_message(id: 'm1')]);
      await cubit.loadRoom();

      // The history fetch and the socket can race over the same message.
      incoming.add(_message(id: 'm1'));
      await Future<void>.delayed(Duration.zero);

      expect((cubit.state as ChatRoomReady).messages, hasLength(1));
    });

    test('marks a message read as it arrives, since the user is looking at it',
        () async {
      await cubit.loadRoom();
      clearInteractions(chatRepository);

      incoming.add(_message(id: 'm1'));
      await Future<void>.delayed(Duration.zero);

      // Otherwise the dashboard badge would claim unread messages the
      // user had just watched arrive.
      verify(() => chatRepository.markAllAsRead()).called(1);
    });

    test('does not mark read for a message it ignores', () async {
      await cubit.loadRoom();
      clearInteractions(chatRepository);

      incoming.add(_message(id: 'other', roomId: 'another-room'));
      await Future<void>.delayed(Duration.zero);

      verifyNever(() => chatRepository.markAllAsRead());
    });

    test('ignores notices and messages for other rooms', () async {
      await cubit.loadRoom();

      incoming.add(_message(id: 'join-1', type: 'join'));
      incoming.add(_message(id: 'other', roomId: 'another-room'));
      await Future<void>.delayed(Duration.zero);

      expect((cubit.state as ChatRoomReady).messages, isEmpty);
    });

    test(
        'marks the room disconnected when the stream closes, keeping the '
        'conversation on screen', () async {
      when(
        () => chatRepository.fetchHistory(
          clientId: any(named: 'clientId'),
          roomId: any(named: 'roomId'),
          limit: any(named: 'limit'),
        ),
      ).thenAnswer((_) async => <ChatMessage>[_message(id: 'm1')]);
      await cubit.loadRoom();
      expect((cubit.state as ChatRoomReady).isConnected, isTrue);

      await incoming.close();
      await Future<void>.delayed(Duration.zero);

      final ChatRoomReady state = cubit.state as ChatRoomReady;
      expect(state.isConnected, isFalse);
      expect(state.messages, hasLength(1));
    });

    test('marks the room disconnected on a stream error', () async {
      await cubit.loadRoom();

      incoming.addError(StateError('socket died'));
      await Future<void>.delayed(Duration.zero);

      expect((cubit.state as ChatRoomReady).isConnected, isFalse);
    });
  });

  group('sendMessage', () {
    test('hands the content to the repository', () async {
      when(() => chatRepository.sendMessage(any())).thenReturn(null);
      await cubit.loadRoom();

      cubit.sendMessage('مرحبا');

      verify(() => chatRepository.sendMessage('مرحبا')).called(1);
    });

    test('does not send blank content', () async {
      when(() => chatRepository.sendMessage(any())).thenReturn(null);
      await cubit.loadRoom();

      cubit.sendMessage('   ');

      verifyNever(() => chatRepository.sendMessage(any()));
    });

    test(
        'does not append the message locally, avoiding a duplicate when the '
        'backend echoes it back', () async {
      when(() => chatRepository.sendMessage(any())).thenReturn(null);
      await cubit.loadRoom();

      cubit.sendMessage('مرحبا');
      await Future<void>.delayed(Duration.zero);

      expect((cubit.state as ChatRoomReady).messages, isEmpty);
    });
  });

  test('close leaves the shared socket open for the dashboard', () async {
    await cubit.loadRoom();

    await cubit.close();

    // The dashboard's ChatCubit owns the socket and is still mounted
    // beneath this route; disconnecting here would kill its badge.
    verifyNever(() => chatRepository.disconnect());
  });
}
