import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/data/datasources/queue_socket_data_source.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/data/repositories/queue_repository_impl.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/domain/entities/clinic.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/domain/entities/clinic_queue.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/domain/entities/queue_reservation.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/domain/repositories/queue_repository.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/presentation/bloc/queue_bloc.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/presentation/pages/queue_dashboard_page.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/presentation/widgets/position_indicator.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/presentation/widgets/queue_card.dart';
import 'package:mizan_frontend/shared/design_system/theme/app_theme.dart';
import 'package:mizan_frontend/shared/design_system/theme/color_scheme.dart';
import 'package:mizan_frontend/shared/exceptions/network_exception.dart';
import 'package:mocktail/mocktail.dart';

class MockQueueRepository extends Mock implements QueueRepository {}

ClinicQueue _queue({
  String id = 'c1',
  String name = 'عيادة الأمل',
  int waiting = 3,
  int serviceMinutes = 8,
  bool accepting = true,
}) {
  return ClinicQueue(
    clinic: Clinic(
      id: id,
      name: name,
      specialty: 'طب عام',
      district: 'وهران',
    ),
    waitingCount: waiting,
    averageServiceMinutes: serviceMinutes,
    isAcceptingPatients: accepting,
  );
}

QueueReservation _reservation({
  int position = 2,
  bool isInConsultation = false,
}) =>
    QueueReservation(
      id: 'r1',
      clinicId: 'c1',
      clinicName: 'عيادة الأمل',
      position: position,
      estimatedWaitMinutes: 16,
      joinedAt: DateTime(2026),
      isInConsultation: isInConsultation,
    );

void main() {
  late MockQueueRepository repository;

  void stubQueues(
    List<ClinicQueue> queues, {
    QueueReservation? reservation,
    bool isShowcase = false,
  }) {
    when(() => repository.fetchQueues()).thenAnswer(
      (_) async => QueueSnapshot(
        queues: queues,
        reservation: reservation,
        isShowcaseData: isShowcase,
      ),
    );
  }

  setUp(() {
    repository = MockQueueRepository();
    // Live updates are covered in `queue_live_updates_test.dart`; here
    // an empty stream keeps the socket out of the way of layout tests.
    when(() => repository.watchQueue(any()))
        .thenAnswer((_) => const Stream<ClinicQueueUpdate>.empty());
    stubQueues(<ClinicQueue>[_queue()]);
  });

  Widget wrap(Widget child) {
    return MaterialApp(
      theme: AppTheme.light,
      locale: const Locale('ar'),
      localizationsDelegates: const <LocalizationsDelegate<dynamic>>[
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: const <Locale>[Locale('ar')],
      home: child,
    );
  }

  Future<void> pumpPage(WidgetTester tester) async {
    await tester.pumpWidget(
      wrap(
        QueueDashboardPage(
          queueCubit: QueueDashboardCubit(repository: repository),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  group('layout', () {
    testWidgets('shows the Arabic title and a card per clinic',
        (WidgetTester tester) async {
      stubQueues(<ClinicQueue>[
        _queue(id: 'c1', name: 'عيادة الأمل'),
        _queue(id: 'c2', name: 'مركز النور'),
      ]);

      await pumpPage(tester);

      expect(find.text('طابور العيادات'), findsOneWidget);
      expect(find.byType(QueueCard), findsNWidgets(2));
      expect(find.text('عيادة الأمل'), findsOneWidget);
      expect(find.text('مركز النور'), findsOneWidget);
    });

    testWidgets('renders right-to-left', (WidgetTester tester) async {
      await pumpPage(tester);

      expect(
        Directionality.of(tester.element(find.text('طابور العيادات'))),
        TextDirection.rtl,
      );
    });

    testWidgets('uses the Mizan navy app bar', (WidgetTester tester) async {
      await pumpPage(tester);

      final AppBar appBar = tester.widget<AppBar>(find.byType(AppBar));
      final Color? resolved = appBar.backgroundColor ??
          Theme.of(tester.element(find.byType(AppBar)))
              .appBarTheme
              .backgroundColor;
      expect(resolved, MizanColors.navy);
    });

    testWidgets('shows the waiting count and derived wait time',
        (WidgetTester tester) async {
      stubQueues(<ClinicQueue>[_queue(waiting: 3, serviceMinutes: 8)]);

      await pumpPage(tester);

      expect(find.text('3 في الانتظار'), findsOneWidget);
      expect(find.text('حوالي 24 دقيقة'), findsOneWidget);
    });

    testWidgets('an empty queue reads as no wait rather than zero minutes',
        (WidgetTester tester) async {
      stubQueues(<ClinicQueue>[_queue(waiting: 0)]);

      await pumpPage(tester);

      expect(find.text('لا أحد ينتظر'), findsOneWidget);
      expect(find.text('بدون انتظار'), findsOneWidget);
    });

    testWidgets('shows a spinner while the query is in flight',
        (WidgetTester tester) async {
      final Completer<QueueSnapshot> pending = Completer<QueueSnapshot>();
      when(() => repository.fetchQueues()).thenAnswer((_) => pending.future);

      await tester.pumpWidget(
        wrap(
          QueueDashboardPage(
            queueCubit: QueueDashboardCubit(repository: repository),
          ),
        ),
      );
      await tester.pump();

      expect(find.byType(CircularProgressIndicator), findsOneWidget);

      pending.complete(
        QueueSnapshot(
          queues: <ClinicQueue>[_queue()],
          reservation: null,
          isShowcaseData: false,
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(QueueCard), findsOneWidget);
    });
  });

  group('graceful degradation', () {
    testWidgets('shows the showcase notice only for illustrative queues',
        (WidgetTester tester) async {
      stubQueues(<ClinicQueue>[_queue()], isShowcase: true);

      await pumpPage(tester);

      expect(find.textContaining('طوابير تجريبية'), findsOneWidget);
      // Said plainly, because a wait time is something a patient acts
      // on.
      expect(
          find.textContaining('لا تعكس أوقات انتظار حقيقية'), findsOneWidget);
    });

    testWidgets('does not claim showcase data when the queues are live',
        (WidgetTester tester) async {
      await pumpPage(tester);

      expect(find.textContaining('طوابير تجريبية'), findsNothing);
    });

    testWidgets('shows a clear message when no clinic is running a queue',
        (WidgetTester tester) async {
      stubQueues(<ClinicQueue>[]);

      await pumpPage(tester);

      expect(find.text('لا توجد طوابير نشطة'), findsOneWidget);
      expect(find.byType(QueueCard), findsNothing);
    });

    testWidgets('surfaces a load failure with a working retry',
        (WidgetTester tester) async {
      when(() => repository.fetchQueues())
          .thenThrow(const NetworkException('تعذّر الاتصال بالخادم.'));

      await pumpPage(tester);

      expect(find.text('تعذّر الاتصال بالخادم.'), findsOneWidget);

      stubQueues(<ClinicQueue>[_queue()]);
      await tester.tap(find.text('إعادة المحاولة'));
      await tester.pumpAndSettle();

      expect(find.byType(QueueCard), findsOneWidget);
    });

    testWidgets('a clinic that is closed offers no way to join',
        (WidgetTester tester) async {
      stubQueues(<ClinicQueue>[_queue(accepting: false)]);

      await pumpPage(tester);

      expect(find.text('لا تستقبل حجوزات حالياً'), findsOneWidget);
      expect(find.text('احجز دورك'), findsNothing);
    });
  });

  group('joining a queue', () {
    testWidgets('a successful join refreshes and confirms',
        (WidgetTester tester) async {
      when(() => repository.joinQueue(any())).thenAnswer(
        (_) async => _reservation(),
      );
      await pumpPage(tester);

      stubQueues(<ClinicQueue>[_queue()], reservation: _reservation());
      await tester.tap(find.text('احجز دورك'));
      await tester.pumpAndSettle();

      verify(() => repository.joinQueue('c1')).called(1);
      expect(find.text('تم حجز دورك بنجاح.'), findsOneWidget);
      expect(find.byType(PositionIndicator), findsOneWidget);
    });

    testWidgets('says plainly when the service is not available yet',
        (WidgetTester tester) async {
      // The degradation that must NOT be silent: a reservation is never
      // faked, so the patient must not be left believing they hold one.
      when(() => repository.joinQueue(any()))
          .thenThrow(const QueueServiceUnavailable());
      await pumpPage(tester);

      await tester.tap(find.text('احجز دورك'));
      await tester.pumpAndSettle();

      expect(find.textContaining('غير متاحة بعد'), findsOneWidget);
      expect(find.byType(PositionIndicator), findsNothing);
    });

    testWidgets('surfaces a refusal from the backend',
        (WidgetTester tester) async {
      when(() => repository.joinQueue(any())).thenThrow(
        const NetworkException('لديك دور محجوز بالفعل في هذه العيادة.'),
      );
      await pumpPage(tester);

      await tester.tap(find.text('احجز دورك'));
      await tester.pumpAndSettle();

      expect(
        find.text('لديك دور محجوز بالفعل في هذه العيادة.'),
        findsOneWidget,
      );
    });
  });

  group('the caller\'s own place', () {
    testWidgets('is pinned above the list', (WidgetTester tester) async {
      // "Where am I in the queue" is what this screen exists to answer;
      // it should not require finding the right card first.
      stubQueues(<ClinicQueue>[_queue()],
          reservation: _reservation(position: 2));

      await pumpPage(tester);

      expect(find.text('يسبقك 2 أشخاص'), findsOneWidget);
      expect(
        tester.getCenter(find.byType(PositionIndicator)).dy,
        lessThan(tester.getCenter(find.byType(QueueCard)).dy),
      );
    });

    testWidgets('reads as "your turn now" once the clinic calls you in',
        (WidgetTester tester) async {
      // A patient who has been called in is not "next" — they are being
      // seen. Telling them to keep waiting would send them back to
      // their chair.
      stubQueues(
        <ClinicQueue>[_queue()],
        reservation: _reservation(position: 0, isInConsultation: true),
      );

      await pumpPage(tester);

      expect(find.text('حان دورك الآن'), findsOneWidget);
      expect(find.text('أنت التالي'), findsNothing);
      expect(find.text('تفضّل بالدخول إلى العيادة'), findsOneWidget);
      // "Expected wait: 0 minutes" is true but useless at that point.
      expect(find.textContaining('الوقت المتوقع'), findsNothing);
    });

    testWidgets('reads as "you are next" at the front',
        (WidgetTester tester) async {
      stubQueues(<ClinicQueue>[_queue()],
          reservation: _reservation(position: 0));

      await pumpPage(tester);

      expect(find.text('أنت التالي'), findsOneWidget);
    });

    testWidgets('the matching clinic offers no second booking',
        (WidgetTester tester) async {
      stubQueues(<ClinicQueue>[_queue()], reservation: _reservation());

      await pumpPage(tester);

      expect(find.text('لديك دور محجوز هنا'), findsOneWidget);
      expect(find.text('احجز دورك'), findsNothing);
    });

    testWidgets('can be cancelled', (WidgetTester tester) async {
      when(() => repository.leaveQueue(any())).thenAnswer((_) async {});
      stubQueues(<ClinicQueue>[_queue()], reservation: _reservation());
      await pumpPage(tester);

      stubQueues(<ClinicQueue>[_queue()]);
      await tester.tap(find.text('إلغاء الدور'));
      await tester.pumpAndSettle();

      verify(() => repository.leaveQueue('r1')).called(1);
      expect(find.text('تم إلغاء دورك.'), findsOneWidget);
      expect(find.byType(PositionIndicator), findsNothing);
    });
  });
}
