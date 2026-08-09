import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/data/datasources/queue_local_datasource.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/data/datasources/queue_remote_datasource.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/data/repositories/queue_repository_impl.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/domain/entities/clinic.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/domain/entities/clinic_queue.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/domain/entities/queue_reservation.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/domain/repositories/queue_repository.dart';
import 'package:mizan_frontend/shared/exceptions/network_exception.dart';
import 'package:mocktail/mocktail.dart';

class MockQueueRemoteDataSource extends Mock implements QueueRemoteDataSource {}

DioException _dioError({int? statusCode, DioExceptionType? type}) {
  final RequestOptions options = RequestOptions(path: '/queues');
  return DioException(
    requestOptions: options,
    type: type ?? DioExceptionType.badResponse,
    response: statusCode == null
        ? null
        : Response<dynamic>(requestOptions: options, statusCode: statusCode),
  );
}

ClinicQueue _queue({String id = 'c1', int waiting = 2}) {
  return ClinicQueue(
    clinic:
        Clinic(id: id, name: 'عيادة', specialty: 'طب عام', district: 'وهران'),
    waitingCount: waiting,
    averageServiceMinutes: 10,
    isAcceptingPatients: true,
  );
}

void main() {
  late MockQueueRemoteDataSource remoteDataSource;
  late QueueRepositoryImpl repository;

  setUp(() {
    remoteDataSource = MockQueueRemoteDataSource();
    repository = QueueRepositoryImpl(remoteDataSource: remoteDataSource);
  });

  group('live data', () {
    test('returns queues from the API and does not flag them as showcase',
        () async {
      when(() => remoteDataSource.fetchQueues()).thenAnswer(
        (_) async => RemoteQueueSnapshot(
          queues: <ClinicQueue>[_queue()],
          reservation: null,
        ),
      );

      final QueueSnapshot snapshot = await repository.fetchQueues();

      expect(snapshot.queues.single.clinic.id, 'c1');
      expect(snapshot.isShowcaseData, isFalse);
    });

    test('carries the caller\'s reservation through', () async {
      final QueueReservation reservation = QueueReservation(
        id: 'r1',
        clinicId: 'c1',
        clinicName: 'عيادة',
        position: 3,
        estimatedWaitMinutes: 30,
        joinedAt: DateTime(2026),
      );
      when(() => remoteDataSource.fetchQueues()).thenAnswer(
        (_) async => RemoteQueueSnapshot(
          queues: <ClinicQueue>[_queue()],
          reservation: reservation,
        ),
      );

      expect((await repository.fetchQueues()).reservation, reservation);
    });
  });

  group('graceful degradation while the API does not exist', () {
    test('falls back to showcase queues on a 404', () async {
      when(() => remoteDataSource.fetchQueues())
          .thenThrow(_dioError(statusCode: 404));

      final QueueSnapshot snapshot = await repository.fetchQueues();

      expect(snapshot.queues, isNotEmpty);
      expect(snapshot.isShowcaseData, isTrue);
    });

    test('falls back on a 501 as well', () async {
      when(() => remoteDataSource.fetchQueues())
          .thenThrow(_dioError(statusCode: 501));

      expect((await repository.fetchQueues()).isShowcaseData, isTrue);
    });

    test('never fabricates a reservation', () async {
      // A wait time can be illustrated; a held place cannot. Showing a
      // reservation the clinic has never heard of would send a patient
      // to a waiting room expecting them.
      when(() => remoteDataSource.fetchQueues())
          .thenThrow(_dioError(statusCode: 404));

      expect((await repository.fetchQueues()).reservation, isNull);
    });

    test('refuses to join rather than faking a place in the queue', () async {
      when(() => remoteDataSource.joinQueue(any()))
          .thenThrow(_dioError(statusCode: 404));

      await expectLater(
        () => repository.joinQueue('c1'),
        throwsA(isA<QueueServiceUnavailable>()),
      );
    });

    test('the refusal explains itself in Arabic', () async {
      when(() => remoteDataSource.joinQueue(any()))
          .thenThrow(_dioError(statusCode: 501));

      await expectLater(
        () => repository.joinQueue('c1'),
        throwsA(
          isA<NetworkException>().having(
            (NetworkException e) => e.message,
            'message',
            contains('غير متاحة بعد'),
          ),
        ),
      );
    });
  });

  group('real failures are not disguised as showcase data', () {
    test('a 500 surfaces as an error', () async {
      when(() => remoteDataSource.fetchQueues())
          .thenThrow(_dioError(statusCode: 500));

      await expectLater(
        () => repository.fetchQueues(),
        throwsA(isA<NetworkException>()),
      );
    });

    test('being offline surfaces as an error', () async {
      // Quietly showing invented waiting times to someone whose network
      // is down could send them to a clinic on made-up information.
      when(() => remoteDataSource.fetchQueues())
          .thenThrow(_dioError(type: DioExceptionType.connectionError));

      await expectLater(
        () => repository.fetchQueues(),
        throwsA(isA<NetworkException>()),
      );
    });

    test('a 401 surfaces as an error', () async {
      when(() => remoteDataSource.fetchQueues())
          .thenThrow(_dioError(statusCode: 401));

      await expectLater(
        () => repository.fetchQueues(),
        throwsA(isA<NetworkException>()),
      );
    });
  });

  group('reservation error mapping', () {
    const Map<int, String> expected = <int, String>{
      403: 'لا تملك صلاحية',
      409: 'لديك دور محجوز بالفعل',
      410: 'انتهت صلاحية',
      422: 'لا تستقبل حجوزات',
    };

    for (final MapEntry<int, String> entry in expected.entries) {
      test('maps ${entry.key} to its own Arabic message', () async {
        when(() => remoteDataSource.joinQueue(any()))
            .thenThrow(_dioError(statusCode: entry.key));

        await expectLater(
          () => repository.joinQueue('c1'),
          throwsA(
            isA<NetworkException>().having(
              (NetworkException e) => e.message,
              'message',
              contains(entry.value),
            ),
          ),
        );
      });
    }
  });

  group('showcase catalogue shape', () {
    test('covers every state the screen can render', () {
      // Otherwise a state would be unreachable without a backend, and
      // therefore never reviewed.
      final List<ClinicQueue> queues =
          const QueueLocalDataSource().showcaseQueues();

      expect(queues.any((ClinicQueue q) => q.isEmpty), isTrue,
          reason: 'no empty queue');
      expect(queues.any((ClinicQueue q) => !q.isAcceptingPatients), isTrue,
          reason: 'no closed clinic');
      expect(
          queues.any((ClinicQueue q) => q.estimatedWaitMinutes >= 45), isTrue,
          reason: 'no long wait');
    });

    test('wait time is derived from the position and the service rate', () {
      // Computed rather than taken from the server, so the number on
      // screen always agrees with the position beside it.
      expect(_queue(waiting: 4).estimatedWaitMinutes, 40);
      expect(_queue(waiting: 0).estimatedWaitMinutes, 0);
    });
  });
}
