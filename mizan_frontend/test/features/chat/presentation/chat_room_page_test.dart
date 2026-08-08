import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/features/auth/data/auth_repository.dart';
import 'package:mizan_frontend/features/auth/domain/entities/auth_user.dart';
import 'package:mizan_frontend/features/chat/data/chat_exceptions.dart';
import 'package:mizan_frontend/features/chat/data/chat_message.dart';
import 'package:mizan_frontend/features/chat/data/chat_repository.dart';
import 'package:mizan_frontend/features/chat/presentation/pages/chat_room_page.dart';
import 'package:mizan_frontend/features/chat/presentation/state/chat_room_cubit.dart';
import 'package:mizan_frontend/features/chat/presentation/widgets/chat_message_bubble.dart';
import 'package:mizan_frontend/shared/design_system/theme/app_theme.dart';
import 'package:mizan_frontend/shared/design_system/theme/color_scheme.dart';
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
}) {
  return ChatMessage.fromJson(<String, dynamic>{
    'id': id,
    'room_id': kDefaultChatRoomId,
    'sender_id': senderId,
    'content': content,
    'type': 'text',
    'created_at': '2026-01-01T09:05:00Z',
  });
}

void main() {
  late MockChatRepository chatRepository;
  late MockAuthRepository authRepository;
  late StreamController<ChatMessage> incoming;

  setUp(() {
    chatRepository = MockChatRepository();
    authRepository = MockAuthRepository();
    incoming = StreamController<ChatMessage>.broadcast();

    when(() => authRepository.getCurrentUser()).thenAnswer((_) async => _alice);
    when(() => chatRepository.isConnected).thenReturn(true);
    when(() => chatRepository.incomingMessages)
        .thenAnswer((_) => incoming.stream);
    when(() => chatRepository.markAllAsRead()).thenReturn(null);
    when(() => chatRepository.sendMessage(any())).thenReturn(null);
    when(
      () => chatRepository.fetchHistory(
        clientId: any(named: 'clientId'),
        roomId: any(named: 'roomId'),
        limit: any(named: 'limit'),
      ),
    ).thenAnswer((_) async => <ChatMessage>[]);
  });

  tearDown(() async {
    if (!incoming.isClosed) await incoming.close();
  });

  Future<void> pumpPage(WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        locale: const Locale('ar'),
        localizationsDelegates: const <LocalizationsDelegate<dynamic>>[
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: const <Locale>[Locale('ar')],
        home: ChatRoomPage(
          chatRoomCubit: ChatRoomCubit(
            chatRepository: chatRepository,
            authRepository: authRepository,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  group('layout', () {
    testWidgets('shows the Arabic title and a composer',
        (WidgetTester tester) async {
      await pumpPage(tester);

      expect(find.text('الدردشة الآمنة'), findsOneWidget);
      expect(find.byType(TextField), findsOneWidget);
      expect(find.byIcon(Icons.send_rounded), findsOneWidget);
    });

    testWidgets('renders right-to-left', (WidgetTester tester) async {
      await pumpPage(tester);

      expect(
        Directionality.of(tester.element(find.byType(TextField))),
        TextDirection.rtl,
      );
    });

    testWidgets('shows the empty-room placeholder when there is no history',
        (WidgetTester tester) async {
      await pumpPage(tester);

      expect(find.text('لا توجد رسائل بعد'), findsOneWidget);
      expect(find.byType(ChatMessageBubble), findsNothing);
    });

    testWidgets('shows a spinner while the history request is in flight',
        (WidgetTester tester) async {
      final Completer<List<ChatMessage>> pending =
          Completer<List<ChatMessage>>();
      when(
        () => chatRepository.fetchHistory(
          clientId: any(named: 'clientId'),
          roomId: any(named: 'roomId'),
          limit: any(named: 'limit'),
        ),
      ).thenAnswer((_) => pending.future);

      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light,
          locale: const Locale('ar'),
          localizationsDelegates: const <LocalizationsDelegate<dynamic>>[
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: const <Locale>[Locale('ar')],
          home: ChatRoomPage(
            chatRoomCubit: ChatRoomCubit(
              chatRepository: chatRepository,
              authRepository: authRepository,
            ),
          ),
        ),
      );
      await tester.pump();

      expect(find.byType(CircularProgressIndicator), findsOneWidget);

      pending.complete(<ChatMessage>[]);
      await tester.pumpAndSettle();
      expect(find.byType(CircularProgressIndicator), findsNothing);
    });
  });

  group('message list', () {
    testWidgets('renders a bubble per message, newest at the bottom',
        (WidgetTester tester) async {
      when(
        () => chatRepository.fetchHistory(
          clientId: any(named: 'clientId'),
          roomId: any(named: 'roomId'),
          limit: any(named: 'limit'),
        ),
      ).thenAnswer(
        (_) async => <ChatMessage>[
          _message(id: 'm1', content: 'الأقدم'),
          _message(id: 'm2', content: 'الأحدث'),
        ],
      );

      await pumpPage(tester);

      expect(find.byType(ChatMessageBubble), findsNWidgets(2));
      // Oldest-first list in a reversed view puts the newest lowest.
      expect(
        tester.getCenter(find.text('الأحدث')).dy,
        greaterThan(tester.getCenter(find.text('الأقدم')).dy),
      );
    });

    testWidgets('styles and aligns own messages differently from received ones',
        (WidgetTester tester) async {
      when(
        () => chatRepository.fetchHistory(
          clientId: any(named: 'clientId'),
          roomId: any(named: 'roomId'),
          limit: any(named: 'limit'),
        ),
      ).thenAnswer(
        (_) async => <ChatMessage>[
          _message(id: 'm1', senderId: 'bob@example.com', content: 'منه'),
          _message(id: 'm2', senderId: 'alice@example.com', content: 'مني'),
        ],
      );

      await pumpPage(tester);

      final ChatMessageBubble mine = tester.widget<ChatMessageBubble>(
        find.ancestor(
          of: find.text('مني'),
          matching: find.byType(ChatMessageBubble),
        ),
      );
      final ChatMessageBubble theirs = tester.widget<ChatMessageBubble>(
        find.ancestor(
          of: find.text('منه'),
          matching: find.byType(ChatMessageBubble),
        ),
      );
      expect(mine.isMine, isTrue);
      expect(theirs.isMine, isFalse);

      // Gold bubble, white text for the user's own message.
      expect(
        tester.widget<Text>(find.text('مني')).style?.color,
        Colors.white,
      );
      expect(
        tester.widget<Text>(find.text('منه')).style?.color,
        MizanColors.navy,
      );

      // Under RTL, "mine" sits at the directional end, i.e. to the left
      // of a received message.
      expect(
        tester.getCenter(find.text('مني')).dx,
        lessThan(tester.getCenter(find.text('منه')).dx),
      );
    });

    testWidgets('appends a message arriving over the socket, live',
        (WidgetTester tester) async {
      await pumpPage(tester);
      expect(find.text('لا توجد رسائل بعد'), findsOneWidget);

      incoming.add(_message(id: 'm1', content: 'رسالة حية'));
      await tester.pumpAndSettle();

      expect(find.text('رسالة حية'), findsOneWidget);
      expect(find.text('لا توجد رسائل بعد'), findsNothing);
    });
  });

  group('sending', () {
    testWidgets('sends the typed text and clears the field immediately',
        (WidgetTester tester) async {
      await pumpPage(tester);

      await tester.enterText(find.byType(TextField), 'السلام عليكم');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.send_rounded));
      await tester.pump();

      verify(() => chatRepository.sendMessage('السلام عليكم')).called(1);
      expect(
        tester.widget<TextField>(find.byType(TextField)).controller?.text,
        isEmpty,
      );
    });

    testWidgets('does not send blank input', (WidgetTester tester) async {
      await pumpPage(tester);

      await tester.enterText(find.byType(TextField), '   ');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.send_rounded));
      await tester.pump();

      verifyNever(() => chatRepository.sendMessage(any()));
    });

    testWidgets('surfaces a send failure rather than losing the message',
        (WidgetTester tester) async {
      when(() => chatRepository.sendMessage(any())).thenThrow(
        const ChatConnectionException(
          'لا يوجد اتصال بخدمة الدردشة. لم يتم إرسال الرسالة.',
        ),
      );

      await pumpPage(tester);
      await tester.enterText(find.byType(TextField), 'مرحبا');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.send_rounded));
      await tester.pump();

      expect(
        find.text('لا يوجد اتصال بخدمة الدردشة. لم يتم إرسال الرسالة.'),
        findsOneWidget,
      );
    });

    testWidgets('disables the composer once the connection drops',
        (WidgetTester tester) async {
      await pumpPage(tester);
      expect(tester.widget<TextField>(find.byType(TextField)).enabled, isTrue);

      await incoming.close();
      await tester.pumpAndSettle();

      expect(tester.widget<TextField>(find.byType(TextField)).enabled, isFalse);
      expect(find.text('الاتصال بخدمة الدردشة منقطع'), findsOneWidget);
    });
  });

  group('history failure', () {
    testWidgets('shows the error with a working retry',
        (WidgetTester tester) async {
      when(
        () => chatRepository.fetchHistory(
          clientId: any(named: 'clientId'),
          roomId: any(named: 'roomId'),
          limit: any(named: 'limit'),
        ),
      ).thenThrow(const NetworkException('تعذّر الاتصال بالخادم.'));

      await pumpPage(tester);

      expect(find.text('تعذّر الاتصال بالخادم.'), findsOneWidget);
      expect(find.text('إعادة المحاولة'), findsOneWidget);

      when(
        () => chatRepository.fetchHistory(
          clientId: any(named: 'clientId'),
          roomId: any(named: 'roomId'),
          limit: any(named: 'limit'),
        ),
      ).thenAnswer((_) async => <ChatMessage>[_message(id: 'm1')]);
      await tester.tap(find.text('إعادة المحاولة'));
      await tester.pumpAndSettle();

      expect(find.byType(ChatMessageBubble), findsOneWidget);
    });
  });
}
