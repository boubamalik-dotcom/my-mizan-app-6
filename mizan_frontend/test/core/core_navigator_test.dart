import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/core/core_navigator.dart';
import 'package:mizan_frontend/core/mini_program_loader/mini_program_base.dart';
import 'package:mizan_frontend/core/mini_program_loader/mini_program_loader.dart';

/// Forbidden terms per the strict Mizan Door scope rule: the mini-program
/// must never surface QR-code scanning or payment-related UI.
const List<String> _forbiddenMizanDoorTerms = <String>[
  'qr',
  'scan',
  'payment',
  'pay ',
];

void main() {
  Widget buildTestApp() {
    return const MaterialApp(
      initialRoute: CoreRoutes.dashboard,
      onGenerateRoute: CoreNavigator.onGenerateRoute,
    );
  }

  /// Pumps the host shell on a tall-enough surface that every dashboard
  /// tile is laid out on-screen and tappable, avoiding flaky hit-tests
  /// against tiles that would otherwise fall outside the default
  /// 800x600 test viewport.
  Future<void> pumpDashboard(WidgetTester tester) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(buildTestApp());
  }

  testWidgets(
      'dashboard renders a showcase card for every curated mini-program',
      (WidgetTester tester) async {
    await pumpDashboard(tester);

    expect(find.text('Tawazun Freight AI'), findsOneWidget);
    expect(find.text('Mizan Door'), findsOneWidget);
    expect(find.text('Oran Real Estate'), findsOneWidget);
  });

  testWidgets(
      'dashboard renders the Wallet/Chat fulcrum card and both "scale" section headers',
      (WidgetTester tester) async {
    await pumpDashboard(tester);

    expect(find.text('المحفظة الرقمية'), findsOneWidget);
    expect(find.text('الدردشة الآمنة'), findsOneWidget);
    expect(find.text('خدمات الأفراد والصحة'), findsOneWidget);
    expect(find.text('الأعمال والأصول'), findsOneWidget);
  });

  testWidgets(
      'tapping the Mizan Door card lazily loads and opens the mini-program',
      (WidgetTester tester) async {
    await pumpDashboard(tester);

    await tester.tap(find.text('Mizan Door'));
    // Let the mini-program's (fake, instant) initialize() future resolve
    // and its root widget build.
    await tester.pumpAndSettle();

    expect(find.text('Clinic queue reservations & wait times'), findsWidgets);
  });

  testWidgets(
      'loader reuses an already-cached mini-program instead of reloading it',
      (WidgetTester tester) async {
    await pumpDashboard(tester);

    // Pre-warm the loader outside the widget tree, simulating a
    // mini-program that was already opened earlier in the session.
    final MiniProgram preloaded =
        await MiniProgramLoader.instance.load('oran_real_estate');
    expect(preloaded.isInitialized, isTrue);

    await tester.tap(find.text('Oran Real Estate'));
    await tester.pumpAndSettle();

    // Navigated away from the dashboard, straight to the mini-program's
    // own content.
    expect(find.text('المحفظة الرقمية'), findsNothing);
    expect(find.text('Property listings, tours & agent contact'), findsWidgets);

    // The exact same (already-initialized) instance was reused rather
    // than a fresh one being created and re-initialized.
    final MiniProgram reused =
        await MiniProgramLoader.instance.load('oran_real_estate');
    expect(reused, same(preloaded));
  });

  testWidgets('mizan_door screen never surfaces QR/payment related UI',
      (WidgetTester tester) async {
    await pumpDashboard(tester);

    await tester.tap(find.text('Mizan Door'));
    await tester.pumpAndSettle();

    final Iterable<Text> textWidgets =
        tester.widgetList<Text>(find.byType(Text));
    for (final Text textWidget in textWidgets) {
      final String? value = textWidget.data?.toLowerCase();
      if (value == null) continue;
      for (final String forbidden in _forbiddenMizanDoorTerms) {
        expect(
          value.contains(forbidden),
          isFalse,
          reason: 'Found forbidden term "$forbidden" in Mizan Door text: '
              '"$value"',
        );
      }
    }
  });

  testWidgets('unknown route falls back to the error page',
      (WidgetTester tester) async {
    await pumpDashboard(tester);

    final NavigatorState navigator =
        tester.state<NavigatorState>(find.byType(Navigator));
    navigator.pushNamed('/this-route-does-not-exist');
    await tester.pumpAndSettle();

    expect(find.text('Something went wrong'), findsOneWidget);
  });

  testWidgets('mini-program route without an id falls back to the error page',
      (WidgetTester tester) async {
    await pumpDashboard(tester);

    final NavigatorState navigator =
        tester.state<NavigatorState>(find.byType(Navigator));
    navigator.pushNamed(CoreRoutes.miniProgram);
    await tester.pumpAndSettle();

    expect(find.text('Something went wrong'), findsOneWidget);
  });
}
