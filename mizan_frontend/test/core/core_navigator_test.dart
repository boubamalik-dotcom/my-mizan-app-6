import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/core/core_navigator.dart';
import 'package:mizan_frontend/core/mini_program_loader/mini_program_base.dart';
import 'package:mizan_frontend/core/mini_program_loader/mini_program_loader.dart';
import 'package:mizan_frontend/features/auth/presentation/pages/login_page.dart';
import 'package:mizan_frontend/features/chat/presentation/state/chat_cubit.dart';
import 'package:mizan_frontend/features/chat/presentation/state/chat_state.dart';
import 'package:mizan_frontend/features/dashboard/presentation/pages/dashboard_page.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/data/datasources/queue_local_datasource.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/data/datasources/queue_socket_data_source.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/domain/entities/queue_reservation.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/presentation/bloc/queue_bloc.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/domain/repositories/queue_repository.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/presentation/bloc/queue_state.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/presentation/pages/queue_dashboard_page.dart';
import 'package:mizan_frontend/mini_programs/oran_real_estate/presentation/pages/property_listing_page.dart';
import 'package:mizan_frontend/features/wallet/data/wallet_model.dart';
import 'package:mizan_frontend/features/wallet/presentation/state/wallet_cubit.dart';
import 'package:mizan_frontend/features/wallet/presentation/state/wallet_state.dart';

/// Forbidden terms per the strict Mizan Door scope rule: the mini-program
/// must never surface QR-code scanning or payment-related UI.
const List<String> _forbiddenMizanDoorTerms = <String>[
  'qr',
  'scan',
  'payment',
  'pay ',
];

/// A [WalletCubit] that never touches the network: it emits a fixed
/// [WalletLoaded] state instead of running [WalletCubit.loadWalletData]'s
/// real repository call. These tests are about routing, not the Wallet
/// feature itself (see `dashboard_page_test.dart` and
/// `wallet_cubit_test.dart` for that) — without this stub, the
/// dashboard's default `WalletCubit()` would fire a real HTTP request
/// against `ApiEndpoints.baseUrl`'s unroutable test-time address and
/// leave a pending `Timer` once the test tears down before it resolves.
class _StubWalletCubit extends WalletCubit {
  @override
  Future<void> loadWalletData() async {
    emit(
      const WalletLoaded(
        WalletModel(
          walletId: 'test-wallet',
          userId: 'test-user',
          balance: 0,
          currency: 'DZD',
          isLocked: false,
          version: 1,
        ),
      ),
    );
  }
}

/// The chat counterpart of [_StubWalletCubit]: emits a fixed
/// [ChatConnected] state instead of opening a real WebSocket (which
/// would hang against `ApiEndpoints`' unroutable test-time host and
/// leave a pending connection once the test tears down).
class _StubChatCubit extends ChatCubit {
  @override
  Future<void> initializeChat() async {
    emit(const ChatConnected(unreadCount: 3));
  }
}

/// A [QueueDashboardCubit] that never touches the network: it emits a
/// fixed state instead of running the real repository call.
class _StubQueueCubit extends QueueDashboardCubit {
  _StubQueueCubit(this._fixed) : super(repository: _UnusedQueueRepository());

  final QueueState _fixed;

  @override
  Future<void> loadQueues() async => emit(_fixed);
}

/// Never called: [_StubQueueCubit] overrides every method that would
/// reach it.
class _UnusedQueueRepository implements QueueRepository {
  @override
  Future<QueueSnapshot> fetchQueues() =>
      throw UnimplementedError('the stub cubit never loads');

  @override
  Future<QueueReservation> joinQueue(String clinicId) =>
      throw UnimplementedError('the stub cubit never joins');

  @override
  Future<void> leaveQueue(String reservationId) =>
      throw UnimplementedError('the stub cubit never leaves');

  @override
  Stream<ClinicQueueUpdate> watchQueue(String clinicId) =>
      const Stream<ClinicQueueUpdate>.empty();
}

void main() {
  Widget buildTestApp() {
    return MaterialApp(
      home: HostDashboardPage(
        walletCubit: _StubWalletCubit(),
        chatCubit: _StubChatCubit(),
      ),
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

  group('startup route stack', () {
    testWidgets(
        'a multi-segment initial route generates exactly one route, so no '
        'dashboard is built behind the login screen',
        (WidgetTester tester) async {
      // Flutter's default `onGenerateInitialRoutes` expands
      // '/auth/login' into ['/', '/auth', '/auth/login']. Because '/' is
      // the dashboard, the default would build a HostDashboardPage
      // beneath the login screen before anyone signed in — firing
      // authenticated wallet/chat calls with no token, and leaving two
      // ChatCubits fighting over the shared ChatRepository.
      await tester.pumpWidget(
        const MaterialApp(
          initialRoute: CoreRoutes.login,
          onGenerateInitialRoutes: CoreNavigator.onGenerateInitialRoutes,
          onGenerateRoute: CoreNavigator.onGenerateRoute,
        ),
      );
      // A single pump, not pumpAndSettle: the login screen's
      // session-restore spinner animates indefinitely.
      await tester.pump();

      expect(find.byType(LoginPage), findsOneWidget);
      expect(find.byType(HostDashboardPage), findsNothing);
    });

    testWidgets('the generated route is the one that was asked for',
        (WidgetTester tester) async {
      final List<Route<dynamic>> routes =
          CoreNavigator.onGenerateInitialRoutes(CoreRoutes.login);

      expect(routes, hasLength(1));
      expect(routes.single.settings.name, CoreRoutes.login);
    });
  });

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
      'tapping the Tawazun card lazily loads and opens the mini-program',
      (WidgetTester tester) async {
    // Tawazun is the only mini-program still resolved through the
    // loader: Mizan Door and Oran Real Estate both have real screens
    // now and their cards push named routes directly.
    await pumpDashboard(tester);

    await tester.tap(find.text('Tawazun Freight AI'));
    // Let the mini-program's (fake, instant) initialize() future resolve
    // and its root widget build.
    await tester.pumpAndSettle();

    expect(find.text('AI-powered logistics & freight tracking'), findsWidgets);
  });

  testWidgets(
      'loader reuses an already-cached mini-program instead of reloading it',
      (WidgetTester tester) async {
    await pumpDashboard(tester);

    // Uses Tawazun rather than Oran Real Estate: Oran now has a real
    // screen and its dashboard card pushes `CoreRoutes.realEstate`
    // directly, so it no longer exercises the loader.
    final MiniProgram preloaded =
        await MiniProgramLoader.instance.load('tawazun_freight_ai');
    expect(preloaded.isInitialized, isTrue);

    await tester.tap(find.text('Tawazun Freight AI'));
    await tester.pumpAndSettle();

    // Navigated away from the dashboard, straight to the mini-program's
    // own content.
    expect(find.text('المحفظة الرقمية'), findsNothing);
    expect(find.text('AI-powered logistics & freight tracking'), findsWidgets);

    // The exact same (already-initialized) instance was reused rather
    // than a fresh one being created and re-initialized.
    final MiniProgram reused =
        await MiniProgramLoader.instance.load('tawazun_freight_ai');
    expect(reused, same(preloaded));
  });

  testWidgets(
      'the real estate route and the mini-program loader render the same '
      'screen', (WidgetTester tester) async {
    // Both entry points must agree: the dashboard pushes the named
    // route, while anything going through the registry renders
    // `buildRootWidget`. If those diverged, Oran Real Estate would have
    // two different "main screens".
    //
    // Built rather than mounted: `PropertyListingPage` starts a real
    // network request on creation, which has no place in a routing
    // test.
    await tester.pumpWidget(const SizedBox.shrink());
    final BuildContext context = tester.element(find.byType(SizedBox));

    final Route<dynamic> route = CoreNavigator.onGenerateRoute(
      const RouteSettings(name: CoreRoutes.realEstate),
    );
    expect(
      (route as MaterialPageRoute<dynamic>).builder(context),
      isA<PropertyListingPage>(),
    );

    final MiniProgram oran =
        await MiniProgramLoader.instance.load('oran_real_estate');
    expect(oran.buildRootWidget(context), isA<PropertyListingPage>());
  });

  testWidgets('the real mizan_door screen never surfaces QR/payment related UI',
      (WidgetTester tester) async {
    // Scans the actual queue screen — including a reservation banner
    // and every clinic card — rather than the placeholder this used to
    // land on. Mizan Door is scoped to queue management only; anything
    // payment-related belongs to the Digital Wallet feature.
    await tester.pumpWidget(
      MaterialApp(
        home: QueueDashboardPage(
          queueCubit: _StubQueueCubit(
            QueueLoaded(
              queues: const QueueLocalDataSource().showcaseQueues(),
              reservation: QueueReservation(
                id: 'r1',
                clinicId: 'clinic-001',
                clinicName: 'عيادة الأمل للطب العام',
                position: 2,
                estimatedWaitMinutes: 16,
                joinedAt: DateTime(2026, 1, 1),
              ),
              isShowcaseData: true,
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final Iterable<Text> textWidgets =
        tester.widgetList<Text>(find.byType(Text));
    expect(textWidgets, isNotEmpty, reason: 'the screen rendered nothing');

    for (final Text textWidget in textWidgets) {
      final String? value = textWidget.data?.toLowerCase();
      if (value == null) continue;
      for (final String forbidden in _forbiddenMizanDoorTerms) {
        expect(
          value.contains(forbidden),
          isFalse,
          reason: 'mizan_door must not mention "$forbidden": "$value"',
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
