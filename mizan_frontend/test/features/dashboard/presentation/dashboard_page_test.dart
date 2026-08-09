import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/core/core_navigator.dart';
import 'package:mizan_frontend/features/chat/presentation/state/chat_cubit.dart';
import 'package:mizan_frontend/features/chat/presentation/state/chat_state.dart';
import 'package:mizan_frontend/features/dashboard/presentation/pages/dashboard_page.dart';
import 'package:mizan_frontend/features/wallet/data/wallet_model.dart';
import 'package:mizan_frontend/features/wallet/data/wallet_repository.dart';
import 'package:mizan_frontend/features/wallet/presentation/state/wallet_cubit.dart';
import 'package:mizan_frontend/features/wallet/presentation/state/wallet_state.dart';
import 'package:mizan_frontend/shared/exceptions/network_exception.dart';
import 'package:mocktail/mocktail.dart';

class MockWalletRepository extends Mock implements WalletRepository {}

const WalletModel _testWallet = WalletModel(
  walletId: 'wallet-1',
  userId: 'user-1',
  balance: 15000,
  currency: 'DZD',
  isLocked: false,
  version: 1,
);

/// A [WalletCubit] that never touches the network — it emits a fixed
/// [WalletLoaded] state instead of running [WalletCubit.loadWalletData]'s
/// real repository call. Used by every test in this file *except* the
/// "Wallet states" group (which specifically exercises real
/// `WalletCubit` behavior against a mocked [WalletRepository]) — the
/// dashboard's default `WalletCubit()` would otherwise fire a real
/// HTTP request against `ApiEndpoints.baseUrl`'s unroutable test-time
/// address and leave a pending `Timer` once the test tears down
/// before it resolves.
class _StubWalletCubit extends WalletCubit {
  @override
  Future<void> loadWalletData() async {
    emit(const WalletLoaded(_testWallet));
  }
}

/// A [ChatCubit] that emits a fixed state instead of opening a real
/// WebSocket, for the same reason [_StubWalletCubit] avoids real HTTP:
/// a live socket against `ApiEndpoints`' unroutable test-time host
/// would hang and outlive the test.
class _StubChatCubit extends ChatCubit {
  _StubChatCubit(this._state);

  final ChatState _state;

  @override
  Future<void> initializeChat() async {
    emit(_state);
  }
}

void main() {
  /// Wraps [HostDashboardPage] in a minimal `MaterialApp` configured
  /// the same way `main.dart` configures the real app — Arabic
  /// locale + the standard localization delegates — so the ambient
  /// [Directionality] is genuinely RTL, exactly like production,
  /// rather than defaulting to LTR the way an unconfigured test
  /// `MaterialApp` would.
  ///
  /// `onGenerateRoute` stubs [CoreRoutes.miniProgram] with a page that
  /// simply echoes the requested mini-program id, so these tests can
  /// verify *which* mini-program a card navigates to without pulling
  /// in the real [MiniProgramLoader]/placeholder pages (already
  /// covered by `core_navigator_test.dart`).
  Widget buildTestApp({WalletCubit? walletCubit, ChatCubit? chatCubit}) {
    return MaterialApp(
      locale: const Locale('ar'),
      supportedLocales: const <Locale>[Locale('ar')],
      localizationsDelegates: const <LocalizationsDelegate<dynamic>>[
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      home: HostDashboardPage(
        walletCubit: walletCubit ?? _StubWalletCubit(),
        chatCubit:
            chatCubit ?? _StubChatCubit(const ChatConnected(unreadCount: 3)),
      ),
      onGenerateRoute: (RouteSettings settings) {
        if (settings.name == CoreRoutes.miniProgram) {
          return MaterialPageRoute<void>(
            settings: settings,
            builder: (_) => Scaffold(
              body: Text('OPENED_MINI_PROGRAM:${settings.arguments}'),
            ),
          );
        }
        if (settings.name == CoreRoutes.walletDetails) {
          // Stubbed rather than the real page: this file tests the
          // dashboard's wiring, while `wallet_details_page_test.dart`
          // covers the page itself.
          return MaterialPageRoute<bool>(
            settings: settings,
            builder: (_) => const Scaffold(body: Text('OPENED_WALLET_DETAILS')),
          );
        }
        if (settings.name == CoreRoutes.chatRoom) {
          // Stubbed for the same reason; `chat_room_page_test.dart`
          // covers the page.
          return MaterialPageRoute<void>(
            settings: settings,
            builder: (_) => const Scaffold(body: Text('OPENED_CHAT_ROOM')),
          );
        }
        if (settings.name == CoreRoutes.mizanDoor) {
          // Stubbed; `queue_dashboard_page_test.dart` covers the page.
          return MaterialPageRoute<void>(
            settings: settings,
            builder: (_) => const Scaffold(body: Text('OPENED_MIZAN_DOOR')),
          );
        }
        if (settings.name == CoreRoutes.realEstate) {
          // Stubbed likewise; `property_listing_page_test.dart` covers
          // the page.
          return MaterialPageRoute<void>(
            settings: settings,
            builder: (_) => const Scaffold(body: Text('OPENED_REAL_ESTATE')),
          );
        }
        return null;
      },
    );
  }

  /// A tall enough surface that every dashboard section is laid out
  /// on-screen and tappable, mirroring `core_navigator_test.dart`'s
  /// `pumpDashboard` helper.
  Future<void> pumpDashboard(
    WidgetTester tester, {
    WalletCubit? walletCubit,
    ChatCubit? chatCubit,
  }) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      buildTestApp(walletCubit: walletCubit, chatCubit: chatCubit),
    );
  }

  group('layout & content', () {
    testWidgets('renders the greeting, fulcrum card, and both section headers',
        (WidgetTester tester) async {
      await pumpDashboard(tester);
      await tester.pump();

      expect(find.text('مرحباً بك في منصة الميزان'), findsOneWidget);
      expect(find.text('المحفظة الرقمية'), findsOneWidget);
      expect(find.text('الدردشة الآمنة'), findsOneWidget);
      expect(find.text('خدمات الأفراد والصحة'), findsOneWidget);
      expect(find.text('الأعمال والأصول'), findsOneWidget);
    });

    testWidgets('renders the loaded wallet balance and an unread chat badge',
        (WidgetTester tester) async {
      await pumpDashboard(tester);
      await tester.pumpAndSettle();

      expect(find.text('15,000 DZD'), findsOneWidget);
      expect(find.text('3'), findsOneWidget);
    });

    testWidgets(
        'renders the B2C Mizan Door card and both B2B cards with their '
        'Arabic subtitles', (WidgetTester tester) async {
      await pumpDashboard(tester);

      expect(find.text('Mizan Door'), findsOneWidget);
      expect(find.text('طابور العيادات'), findsOneWidget);

      expect(find.text('Tawazun Freight AI'), findsOneWidget);
      expect(find.text('الشحن والخدمات اللوجستية'), findsOneWidget);

      expect(find.text('Oran Real Estate'), findsOneWidget);
      expect(find.text('العقارات والاستثمار'), findsOneWidget);
    });

    testWidgets(
        'RTL: the wallet half renders to the right of the chat half in the '
        'fulcrum card', (WidgetTester tester) async {
      await pumpDashboard(tester);

      final double walletX = tester.getCenter(find.text('المحفظة الرقمية')).dx;
      final double chatX = tester.getCenter(find.text('الدردشة الآمنة')).dx;

      // On screen, "right" always means a larger x-coordinate — this
      // is exactly what the task requires ("Right side: Wallet, Left
      // side: Chat") and is only guaranteed here because the app's
      // ambient Directionality is RTL, which places a Row's *first*
      // child (Wallet) at the reading-direction start (the right edge).
      expect(walletX, greaterThan(chatX));
    });
  });

  group('wallet states', () {
    late MockWalletRepository repository;

    setUpAll(() {
      registerFallbackValue(_testWallet);
    });

    setUp(() {
      repository = MockWalletRepository();
    });

    testWidgets('shows a gold loading spinner while the wallet is loading',
        (WidgetTester tester) async {
      final Completer<WalletModel> completer = Completer<WalletModel>();
      when(() => repository.getOrCreateWallet())
          .thenAnswer((_) => completer.future);

      await pumpDashboard(
        tester,
        walletCubit: WalletCubit(repository: repository),
      );
      await tester.pump();

      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      final CircularProgressIndicator indicator = tester.widget(
        find.byType(CircularProgressIndicator),
      );
      expect(
        (indicator.valueColor as AlwaysStoppedAnimation<Color>).value,
        const Color(0xFFD4A017),
      );

      // Avoid leaving the completer's future permanently unresolved.
      completer.complete(_testWallet);
      await tester.pumpAndSettle();
    });

    testWidgets(
        'shows the balance formatted with intl.NumberFormat once loaded',
        (WidgetTester tester) async {
      when(() => repository.getOrCreateWallet())
          .thenAnswer((_) async => _testWallet);

      await pumpDashboard(
        tester,
        walletCubit: WalletCubit(repository: repository),
      );
      await tester.pumpAndSettle();

      expect(find.text('15,000 DZD'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsNothing);
    });

    testWidgets('shows a concise retry notice on error, and tapping it retries',
        (WidgetTester tester) async {
      when(() => repository.getOrCreateWallet())
          .thenThrow(const NetworkException('تعذّر الاتصال بالخادم.'));

      await pumpDashboard(
        tester,
        walletCubit: WalletCubit(repository: repository),
      );
      await tester.pumpAndSettle();

      expect(find.text('خطأ في التحديث'), findsOneWidget);
      verify(() => repository.getOrCreateWallet()).called(1);

      when(() => repository.getOrCreateWallet())
          .thenAnswer((_) async => _testWallet);
      await tester.tap(find.text('خطأ في التحديث'));
      await tester.pumpAndSettle();

      expect(find.text('15,000 DZD'), findsOneWidget);
      verify(() => repository.getOrCreateWallet()).called(1);
    });
  });

  group('chat states', () {
    testWidgets('connecting shows a miniature progress indicator, no badge',
        (WidgetTester tester) async {
      await pumpDashboard(
        tester,
        chatCubit: _StubChatCubit(const ChatConnecting()),
      );
      await tester.pump();

      expect(find.text('جارٍ الاتصال…'), findsOneWidget);
      // Two spinners would mean the wallet is still loading too; the
      // stub wallet cubit resolves immediately, so this one is chat's.
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      expect(find.text('3'), findsNothing);
    });

    testWidgets('connected with unread messages shows a gold count badge',
        (WidgetTester tester) async {
      await pumpDashboard(
        tester,
        chatCubit: _StubChatCubit(const ChatConnected(unreadCount: 4)),
      );
      await tester.pump();

      expect(find.text('4'), findsOneWidget);
      expect(find.text('لديك رسائل غير مقروءة'), findsOneWidget);

      final Container badge = tester.widget<Container>(
        find
            .ancestor(
              of: find.text('4'),
              matching: find.byType(Container),
            )
            .first,
      );
      final BoxDecoration decoration = badge.decoration! as BoxDecoration;
      expect(decoration.color, const Color(0xFFD4A017));
    });

    testWidgets('connected with nothing unread shows no badge at all',
        (WidgetTester tester) async {
      await pumpDashboard(
        tester,
        chatCubit: _StubChatCubit(const ChatConnected()),
      );
      await tester.pump();

      expect(find.text('محادثات مشفّرة بالكامل'), findsOneWidget);
      expect(find.text('0'), findsNothing);
      expect(find.byIcon(Icons.cloud_off_rounded), findsNothing);
    });

    testWidgets('a capped badge is shown for more than nine unread messages',
        (WidgetTester tester) async {
      await pumpDashboard(
        tester,
        chatCubit: _StubChatCubit(const ChatConnected(unreadCount: 42)),
      );
      await tester.pump();

      expect(find.text('9+'), findsOneWidget);
      expect(find.text('42'), findsNothing);
    });

    testWidgets('disconnected shows the offline marker',
        (WidgetTester tester) async {
      await pumpDashboard(
        tester,
        chatCubit: _StubChatCubit(const ChatDisconnected()),
      );
      await tester.pump();

      expect(find.byIcon(Icons.cloud_off_rounded), findsOneWidget);
      expect(find.text('غير متصل حاليًا'), findsOneWidget);
    });

    testWidgets('an error also shows the offline marker with its own label',
        (WidgetTester tester) async {
      await pumpDashboard(
        tester,
        chatCubit: _StubChatCubit(const ChatError('تعذّر الاتصال بالخادم.')),
      );
      await tester.pump();

      expect(find.byIcon(Icons.cloud_off_rounded), findsOneWidget);
      expect(find.text('تعذّر الاتصال'), findsOneWidget);
    });
  });

  group('navigation', () {
    testWidgets('tapping the Mizan Door card opens the queue route',
        (WidgetTester tester) async {
      // Like Oran Real Estate, Mizan Door has a real screen now, so its
      // card goes straight to the named route instead of through the
      // mini-program loader. Tawazun below still uses the loader.
      await pumpDashboard(tester);

      await tester.tap(find.text('Mizan Door'));
      await tester.pumpAndSettle();

      expect(find.text('OPENED_MIZAN_DOOR'), findsOneWidget);
    });

    testWidgets('tapping the Tawazun Freight AI card opens it by id',
        (WidgetTester tester) async {
      await pumpDashboard(tester);

      await tester.tap(find.text('Tawazun Freight AI'));
      await tester.pumpAndSettle();

      expect(
        find.text('OPENED_MINI_PROGRAM:tawazun_freight_ai'),
        findsOneWidget,
      );
    });

    testWidgets('tapping the Oran Real Estate card opens the real estate route',
        (WidgetTester tester) async {
      // Unlike the other two mini-programs, Oran has a real screen, so
      // its card goes straight to the named route instead of through
      // the mini-program loader.
      await pumpDashboard(tester);

      await tester.tap(find.text('Oran Real Estate'));
      await tester.pumpAndSettle();

      expect(find.text('OPENED_REAL_ESTATE'), findsOneWidget);
    });

    testWidgets(
        'tapping the wallet half of the fulcrum card opens the wallet details '
        'route', (WidgetTester tester) async {
      await pumpDashboard(tester);
      await tester.pump();

      // Tap the label rather than the balance text: the balance belongs
      // to `WalletBalanceView`, which has its own tap handler for the
      // error-retry case, so going through the half's outer `InkWell`
      // is unambiguous regardless of which wallet state is showing.
      await tester.tap(find.text('المحفظة الرقمية'));
      await tester.pumpAndSettle();

      expect(find.text('OPENED_WALLET_DETAILS'), findsOneWidget);
    });

    testWidgets('tapping the chat half of the fulcrum card opens the chat room',
        (WidgetTester tester) async {
      await pumpDashboard(tester);

      await tester.tap(find.text('الدردشة الآمنة'));
      await tester.pumpAndSettle();

      expect(find.text('OPENED_CHAT_ROOM'), findsOneWidget);
    });
  });
}
