import 'package:dio/dio.dart';

import '../../../../shared/network/api_client.dart';
import '../../../../shared/network/endpoints.dart';
import '../../domain/entities/clinic_queue.dart';
import '../../domain/entities/queue_reservation.dart';
import '../models/queue_model.dart';
import '../models/reservation_model.dart';

/// One `GET /queues` response: every clinic's queue, plus the caller's
/// own reservation if they hold one.
class RemoteQueueSnapshot {
  const RemoteQueueSnapshot({required this.queues, required this.reservation});

  final List<ClinicQueue> queues;
  final QueueReservation? reservation;
}

/// Fetches clinic queues and manages the caller's reservation over HTTP.
///
/// Goes through the app-wide [ApiClient] rather than its own [Dio], so
/// every request this mini-program makes automatically carries the
/// signed-in user's JWT (`AuthInterceptor` attaches the bearer token)
/// and shares the host shell's base URL, timeouts, and forced-logout
/// handling on a 401.
///
/// That matters more here than for a read-only feature: a reservation
/// belongs to a *person*, so joining a queue is only meaningful if the
/// server knows who is asking. A mini-program never manages a session
/// of its own.
class QueueRemoteDataSource {
  QueueRemoteDataSource({ApiClient? apiClient})
      : _apiClient = apiClient ?? ApiClient.instance;

  final ApiClient _apiClient;

  /// `GET /queues` — the current state of every clinic queue.
  ///
  /// Throws the raw [DioException] on failure, for `QueueRepository` to
  /// interpret.
  Future<RemoteQueueSnapshot> fetchQueues() async {
    final Response<dynamic> response = await _apiClient.get(
      ApiEndpoints.clinicQueues,
    );

    final dynamic body = response.data;
    if (body is! Map<String, dynamic> && body is! List) {
      throw FormatException('Unexpected queues response: $body');
    }

    // Accepts either a bare list of queues or an envelope carrying the
    // caller's reservation alongside them, so whichever shape the API
    // ships with, this keeps working.
    final Object? rawQueues =
        body is List ? body : (body as Map<String, dynamic>)['queues'];
    if (rawQueues is! List) {
      throw FormatException('Expected a `queues` list, got: $rawQueues');
    }

    final Object? rawReservation =
        body is Map<String, dynamic> ? body['reservation'] : null;

    return RemoteQueueSnapshot(
      queues: rawQueues
          .cast<Map<String, dynamic>>()
          .map(QueueModel.fromJson)
          .toList(growable: false),
      reservation: rawReservation is Map<String, dynamic>
          ? ReservationModel.fromJson(rawReservation)
          : null,
    );
  }

  /// `POST /queues/{clinicId}/reservations` — take a place in the queue.
  Future<QueueReservation> joinQueue(String clinicId) async {
    final Response<dynamic> response = await _apiClient.post(
      ApiEndpoints.joinClinicQueue(clinicId),
    );

    final dynamic body = response.data;
    if (body is! Map<String, dynamic>) {
      throw FormatException('Unexpected reservation response: $body');
    }
    return ReservationModel.fromJson(body);
  }

  /// `DELETE /queues/reservations/{id}` — give up a reservation.
  Future<void> leaveQueue(String reservationId) async {
    await _apiClient.delete(ApiEndpoints.clinicReservation(reservationId));
  }
}
