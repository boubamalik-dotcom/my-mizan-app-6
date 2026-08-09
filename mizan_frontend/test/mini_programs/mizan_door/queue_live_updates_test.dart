import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/data/datasources/queue_socket_data_source.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/domain/entities/clinic.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/domain/entities/clinic_queue.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/domain/entities/queue_reservation.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/domain/repositories/queue_repository.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/presentation/bloc/queue_bloc.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/presentation/bloc/queue_state.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/presentation/pages/queue_dashboard_page.dart';
import 'package:mocktail/mocktail.dart';

class MockQueueRepository extends Mock implements QueueRepository {}

ClinicQueue _queue({
  String id = 'c1',
  String name = 'عيادة الأمل',
  int waiting = 3,
  int rate = 8,
  int? nowServing,
}) {
  return ClinicQueue(
    clinic: Clinic(id: id, name: name, specialty: 'طب عام', district: 'وهران'),
    waitingCount: waiting,
    averageServiceMinutes: rate,
    isAcceptingPatients: true,
    nowServingTicket: nowServing,
  );
}

ClinicQueueUpdate _update({
  String clinicId = 'c1',
  int waiting = 1,
  int? nowServing,
  bool accepting = true,
  int rate = 8,
}) {
  return ClinicQueueUpdate(
    clinicId: clinicId,
    waitingCount: waiting,
    isAcceptingPatients: accepting,
    averageServiceMinutes: rate,
    nowServingTicket: nowServing,
  );
}

void main() {
  late MockQueueRepository repository;
  late StreamController<ClinicQueueUpdate> live;

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
    live = StreamController<ClinicQueueUpdate>.broadcast();
    when(() => repository.watchQueue(any())).thenAnswer((_) => live.stream);
    stubQueues(<ClinicQueue>[_queue()]);
  });

  tearDown(() async {
    await live.close();
  });

  group('the cubit applies pushed updates', () {
    test('subscribes to every clinic it loaded', () async {
      stubQueues(<ClinicQueue>[_queue(id: 'c1'), _queue(id: 'c2')]);
      final QueueDashboardCubit cubit =
          QueueDashboardCubit(repository: repository);

      await cubit.loadQueues();

      verify(() => repository.watchQueue('c1')).called(1);
      verify(() => repository.watchQueue('c2')).called(1);
      await cubit.close();
    });

    test('never subscribes for the bundled showcase catalogue', () async {
      // There is no server behind it to push anything.
      stubQueues(<ClinicQueue>[_queue()], isShowcase: true);
      final QueueDashboardCubit cubit =
          QueueDashboardCubit(repository: repository);

      await cubit.loadQueues();

      verifyNever(() => repository.watchQueue(any()));
      await cubit.close();
    });

    test('re-renders the queue without any refetch', () async {
      final QueueDashboardCubit cubit =
          QueueDashboardCubit(repository: repository);
      await cubit.loadQueues();
      clearInteractions(repository);

      live.add(_update(waiting: 9, nowServing: 4));
      await Future<void>.delayed(Duration.zero);

      final QueueLoaded state = cubit.state as QueueLoaded;
      expect(state.queues.single.waitingCount, 9);
      expect(state.queues.single.nowServingTicket, 4);
      // The whole point: no second read was needed to show this.
      verifyNever(() => repository.fetchQueues());
      await cubit.close();
    });

    test('an emptied room clears the now-serving ticket', () async {
      stubQueues(<ClinicQueue>[_queue(nowServing: 4)]);
      final QueueDashboardCubit cubit =
          QueueDashboardCubit(repository: repository);
      await cubit.loadQueues();

      live.add(_update(waiting: 0, nowServing: null));
      await Future<void>.delayed(Duration.zero);

      expect(
          (cubit.state as QueueLoaded).queues.single.nowServingTicket, isNull);
      await cubit.close();
    });

    test('keeps the clinic identity the frame does not carry', () async {
      // The update has no name, specialty, or district; it must be
      // merged into the clinic on screen, not replace it.
      final QueueDashboardCubit cubit =
          QueueDashboardCubit(repository: repository);
      await cubit.loadQueues();

      live.add(_update(waiting: 2));
      await Future<void>.delayed(Duration.zero);

      final Clinic clinic = (cubit.state as QueueLoaded).queues.single.clinic;
      expect(clinic.name, 'عيادة الأمل');
      expect(clinic.district, 'وهران');
      await cubit.close();
    });

    test('ignores a frame for a clinic it is not showing', () async {
      final QueueDashboardCubit cubit =
          QueueDashboardCubit(repository: repository);
      await cubit.loadQueues();
      final QueueLoaded before = cubit.state as QueueLoaded;

      live.add(_update(clinicId: 'somewhere-else', waiting: 99));
      await Future<void>.delayed(Duration.zero);

      expect((cubit.state as QueueLoaded).queues, before.queues);
      await cubit.close();
    });

    test('re-reads the caller\'s own place when their clinic moves', () async {
      // The frame carries no patient information, so the position can
      // only come from an authenticated read.
      stubQueues(
        <ClinicQueue>[_queue()],
        reservation: QueueReservation(
          id: 'r1',
          clinicId: 'c1',
          clinicName: 'عيادة الأمل',
          position: 2,
          estimatedWaitMinutes: 16,
          joinedAt: DateTime(2026),
        ),
      );
      final QueueDashboardCubit cubit =
          QueueDashboardCubit(repository: repository);
      await cubit.loadQueues();
      clearInteractions(repository);
      stubQueues(
        <ClinicQueue>[_queue(waiting: 1)],
        reservation: QueueReservation(
          id: 'r1',
          clinicId: 'c1',
          clinicName: 'عيادة الأمل',
          position: 0,
          estimatedWaitMinutes: 0,
          joinedAt: DateTime(2026),
        ),
      );

      live.add(_update(waiting: 1));
      await Future<void>.delayed(const Duration(milliseconds: 600));

      expect((cubit.state as QueueLoaded).reservation!.position, 0);
      await cubit.close();
    });

    test('a burst of updates causes one refetch, not one each', () async {
      stubQueues(
        <ClinicQueue>[_queue()],
        reservation: QueueReservation(
          id: 'r1',
          clinicId: 'c1',
          clinicName: 'عيادة الأمل',
          position: 4,
          estimatedWaitMinutes: 32,
          joinedAt: DateTime(2026),
        ),
      );
      final QueueDashboardCubit cubit =
          QueueDashboardCubit(repository: repository);
      await cubit.loadQueues();
      clearInteractions(repository);

      for (var i = 0; i < 5; i++) {
        live.add(_update(waiting: 5 - i));
      }
      await Future<void>.delayed(const Duration(milliseconds: 600));

      verify(() => repository.fetchQueues()).called(1);
      await cubit.close();
    });

    test('a failed background refresh leaves the queue on screen', () async {
      stubQueues(
        <ClinicQueue>[_queue()],
        reservation: QueueReservation(
          id: 'r1',
          clinicId: 'c1',
          clinicName: 'عيادة الأمل',
          position: 1,
          estimatedWaitMinutes: 8,
          joinedAt: DateTime(2026),
        ),
      );
      final QueueDashboardCubit cubit =
          QueueDashboardCubit(repository: repository);
      await cubit.loadQueues();
      when(() => repository.fetchQueues()).thenThrow(Exception('offline'));

      live.add(_update(waiting: 1));
      await Future<void>.delayed(const Duration(milliseconds: 600));

      // Replacing a working queue with an error because one
      // opportunistic read failed would be the wrong answer.
      expect(cubit.state, isA<QueueLoaded>());
      await cubit.close();
    });

    test('closing cancels the subscriptions', () async {
      final QueueDashboardCubit cubit =
          QueueDashboardCubit(repository: repository);
      await cubit.loadQueues();
      expect(live.hasListener, isTrue);

      await cubit.close();

      expect(live.hasListener, isFalse);
    });
  });

  group('the screen re-renders', () {
    testWidgets('a pushed update changes the card with no interaction',
        (WidgetTester tester) async {
      stubQueues(<ClinicQueue>[_queue(waiting: 3, rate: 8)]);
      await tester.pumpWidget(
        MaterialApp(
          home: QueueDashboardPage(
            queueCubit: QueueDashboardCubit(repository: repository),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('3 في الانتظار'), findsOneWidget);

      live.add(_update(waiting: 1, nowServing: 3));
      await tester.pumpAndSettle();

      expect(find.text('1 في الانتظار'), findsOneWidget);
      expect(find.text('يُخدم الآن رقم 3'), findsOneWidget);
      expect(find.text('3 في الانتظار'), findsNothing);
    });
  });
}
