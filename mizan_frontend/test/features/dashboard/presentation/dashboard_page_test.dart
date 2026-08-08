import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/core/core_navigator.dart';
import 'package:mizan_frontend/features/dashboard/presentation/pages/dashboard_page.dart';

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
  Widget buildTestApp() {
    return MaterialApp(
      locale: const Locale('ar'),
      supportedLocales: const <Locale>[Locale('ar')],
      localizationsDelegates: const <LocalizationsDelegate<dynamic>>[
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      home: HostDashboardPage(),
      onGenerateRoute: (RouteSettings settings) {
        if (settings.name == CoreRoutes.miniProgram) {
          return MaterialPageRoute<void>(
            settings: settings,
            builder: (_) => Scaffold(
              body: Text('OPENED_MINI_PROGRAM:${settings.arguments}'),
            ),
          );
        }
        return null;
      },
    );
  }

  /// A tall enough surface that every dashboard section is laid out
  /// on-screen and tappable, mirroring `core_navigator_test.dart`'s
  /// `pumpDashboard` helper.
  Future<void> pumpDashboard(WidgetTester tester) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(buildTestApp());
  }

  group('layout & content', () {
    testWidgets('renders the greeting, fulcrum card, and both section headers',
        (WidgetTester tester) async {
      await pumpDashboard(tester);

      expect(find.text('مرحباً بك في منصة الميزان'), findsOneWidget);
      expect(find.text('المحفظة الرقمية'), findsOneWidget);
      expect(find.text('الدردشة الآمنة'), findsOneWidget);
      expect(find.text('خدمات الأفراد والصحة'), findsOneWidget);
      expect(find.text('الأعمال والأصول'), findsOneWidget);
    });

    testWidgets('renders a placeholder wallet balance and an unread chat badge',
        (WidgetTester tester) async {
      await pumpDashboard(tester);

      expect(find.text('2,450.00 ر.س'), findsOneWidget);
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

  group('navigation', () {
    testWidgets('tapping the Mizan Door card opens it by id',
        (WidgetTester tester) async {
      await pumpDashboard(tester);

      await tester.tap(find.text('Mizan Door'));
      await tester.pumpAndSettle();

      expect(find.text('OPENED_MINI_PROGRAM:mizan_door'), findsOneWidget);
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

    testWidgets('tapping the Oran Real Estate card opens it by id',
        (WidgetTester tester) async {
      await pumpDashboard(tester);

      await tester.tap(find.text('Oran Real Estate'));
      await tester.pumpAndSettle();

      expect(
        find.text('OPENED_MINI_PROGRAM:oran_real_estate'),
        findsOneWidget,
      );
    });

    testWidgets('tapping the wallet half of the fulcrum card shows a notice',
        (WidgetTester tester) async {
      await pumpDashboard(tester);

      await tester.tap(find.text('المحفظة الرقمية'));
      await tester.pump();

      expect(find.text('المحفظة الرقمية — قريباً.'), findsOneWidget);
    });

    testWidgets('tapping the chat half of the fulcrum card shows a notice',
        (WidgetTester tester) async {
      await pumpDashboard(tester);

      await tester.tap(find.text('الدردشة الآمنة'));
      await tester.pump();

      expect(find.text('الدردشة الآمنة — قريباً.'), findsOneWidget);
    });
  });
}
