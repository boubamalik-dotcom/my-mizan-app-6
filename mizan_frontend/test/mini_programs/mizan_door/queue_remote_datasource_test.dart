import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/data/datasources/queue_remote_datasource.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/domain/entities/queue_reservation.dart';
import 'package:mizan_frontend/shared/network/api_client.dart';
import 'package:mocktail/mocktail.dart';

class MockApiClient extends Mock implements ApiClient {}

Response<dynamic> _response(dynamic data) {
  return Response<dynamic>(
    requestOptions: RequestOptions(path: '/queues'),
    statusCode: 200,
    data: data,
  );
}

Map<String, dynamic> _queueJson(String id) => <String, dynamic>{
      'clinic': <String, dynamic>{
        'id': id,
        'name': 'عيادة الأمل',
        'specialty': 'طب عام',
        'district': 'وهران',
      },
      'waiting_count': 3,
      'average_service_minutes': 8,
      'is_accepting_patients': true,
    };

Map<String, dynamic> _reservationJson() => <String, dynamic>{
      'id': 'r1',
      'clinic_id': 'c1',
      'clinic_name': 'عيادة الأمل',
      'position': 2,
      'estimated_wait_minutes': 16,
      'joined_at': '2026-01-01T09:00:00',
    };

void main() {
  late MockApiClient apiClient;
  late QueueRemoteDataSource dataSource;

  setUp(() {
    apiClient = MockApiClient();
    dataSource = QueueRemoteDataSource(apiClient: apiClient);
  });

  test('goes through the shared ApiClient, so requests inherit the JWT',
      () async {
    // The requirement: a mini-program never manages a session of its
    // own. Using ApiClient means AuthInterceptor attaches the bearer
    // token and handles a 401 exactly as it does for the wallet and
    // chat features.
    when(() => apiClient.get(any(),
        queryParameters:
            any<Map<String, dynamic>>(named: 'queryParameters'))).thenAnswer(
        (_) async => _response(<Map<String, dynamic>>[_queueJson('c1')]));

    final RemoteQueueSnapshot snapshot = await dataSource.fetchQueues();

    expect(snapshot.queues.single.clinic.id, 'c1');
    verify(() => apiClient.get('/queues')).called(1);
  });

  test('joining a queue also goes through the shared client', () async {
    // Matters more for a write than a read: a reservation belongs to a
    // person, so the server has to know who is asking.
    when(() => apiClient.post(any<String>(), data: any<dynamic>(named: 'data')))
        .thenAnswer((_) async => _response(_reservationJson()));

    final QueueReservation reservation = await dataSource.joinQueue('c1');

    expect(reservation.id, 'r1');
    expect(reservation.position, 2);
    verify(() => apiClient.post('/queues/c1/reservations')).called(1);
  });

  test('leaving a queue also goes through the shared client', () async {
    when(() =>
            apiClient.delete(any<String>(), data: any<dynamic>(named: 'data')))
        .thenAnswer((_) async => _response(null));

    await dataSource.leaveQueue('r1');

    verify(() => apiClient.delete('/queues/reservations/r1')).called(1);
  });

  test('percent-encodes ids in the path', () async {
    when(() => apiClient.post(any<String>(), data: any<dynamic>(named: 'data')))
        .thenAnswer((_) async => _response(_reservationJson()));

    await dataSource.joinQueue('clinic/../admin');

    verify(() => apiClient.post('/queues/clinic%2F..%2Fadmin/reservations'))
        .called(1);
  });

  group('response shapes', () {
    test('accepts a bare list of queues', () async {
      when(() => apiClient.get(any(),
          queryParameters:
              any<Map<String, dynamic>>(named: 'queryParameters'))).thenAnswer(
        (_) async => _response(<Map<String, dynamic>>[_queueJson('c1')]),
      );

      final RemoteQueueSnapshot snapshot = await dataSource.fetchQueues();

      expect(snapshot.queues, hasLength(1));
      expect(snapshot.reservation, isNull);
    });

    test('accepts an envelope carrying the reservation alongside', () async {
      when(() => apiClient.get(any(),
          queryParameters:
              any<Map<String, dynamic>>(named: 'queryParameters'))).thenAnswer(
        (_) async => _response(<String, dynamic>{
          'queues': <Map<String, dynamic>>[_queueJson('c1')],
          'reservation': _reservationJson(),
        }),
      );

      final RemoteQueueSnapshot snapshot = await dataSource.fetchQueues();

      expect(snapshot.queues, hasLength(1));
      expect(snapshot.reservation?.id, 'r1');
    });

    test('accepts a flattened clinic rather than a nested one', () async {
      when(() => apiClient.get(any(),
          queryParameters:
              any<Map<String, dynamic>>(named: 'queryParameters'))).thenAnswer(
        (_) async => _response(<Map<String, dynamic>>[
          <String, dynamic>{
            'id': 'c9',
            'name': 'عيادة',
            'waiting_count': 1,
            'average_service_minutes': 5,
          }
        ]),
      );

      final RemoteQueueSnapshot snapshot = await dataSource.fetchQueues();

      expect(snapshot.queues.single.clinic.id, 'c9');
    });

    test('rejects a shape it cannot read rather than returning nothing',
        () async {
      when(() => apiClient.get(any(),
              queryParameters:
                  any<Map<String, dynamic>>(named: 'queryParameters')))
          .thenAnswer((_) async => _response('not a list'));

      await expectLater(
        () => dataSource.fetchQueues(),
        throwsA(isA<FormatException>()),
      );
    });
  });
}
