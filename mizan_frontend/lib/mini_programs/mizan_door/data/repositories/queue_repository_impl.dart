import 'package:dio/dio.dart';

import '../../../../shared/exceptions/network_exception.dart';
import '../../domain/entities/queue_reservation.dart';
import '../../domain/repositories/queue_repository.dart';
import '../datasources/queue_local_datasource.dart';
import '../datasources/queue_remote_datasource.dart';

/// Thrown when the queue API is not deployed yet and the caller asked
/// for something that cannot be faked.
///
/// Reading a queue degrades to showcase data. Joining one cannot: a
/// reservation is a promise that a clinic is expecting you, and
/// inventing one locally would send a patient to a waiting room that
/// has never heard of them.
class QueueServiceUnavailable extends NetworkException {
  const QueueServiceUnavailable()
      : super(
          'خدمة الطوابير غير متاحة بعد. لا يمكن حجز دور في الوقت الحالي.',
          statusCode: 501,
        );
}

/// Serves clinic queues from the API, falling back to the bundled
/// showcase catalogue only while the API does not exist.
class QueueRepositoryImpl implements QueueRepository {
  QueueRepositoryImpl({
    QueueRemoteDataSource? remoteDataSource,
    QueueLocalDataSource localDataSource = const QueueLocalDataSource(),
  })  : _remoteDataSource = remoteDataSource ?? QueueRemoteDataSource(),
        _localDataSource = localDataSource;

  final QueueRemoteDataSource _remoteDataSource;
  final QueueLocalDataSource _localDataSource;

  @override
  Future<QueueSnapshot> fetchQueues() async {
    try {
      final RemoteQueueSnapshot snapshot =
          await _remoteDataSource.fetchQueues();
      return QueueSnapshot(
        queues: snapshot.queues,
        reservation: snapshot.reservation,
        isShowcaseData: false,
      );
    } on DioException catch (error) {
      if (_isEndpointMissing(error)) {
        return QueueSnapshot(
          queues: _localDataSource.showcaseQueues(),
          // No reservation is ever fabricated: the screen must not
          // suggest a patient holds a place they do not.
          reservation: null,
          isShowcaseData: true,
        );
      }
      throw NetworkException.fromDioException(error);
    }
  }

  @override
  Future<QueueReservation> joinQueue(String clinicId) async {
    try {
      return await _remoteDataSource.joinQueue(clinicId);
    } on DioException catch (error) {
      if (_isEndpointMissing(error)) {
        // Deliberately *not* degraded to a local reservation. Reading a
        // queue can be illustrated; holding a place cannot be
        // pretended.
        throw const QueueServiceUnavailable();
      }
      throw _mapReservationError(error);
    }
  }

  @override
  Future<void> leaveQueue(String reservationId) async {
    try {
      await _remoteDataSource.leaveQueue(reservationId);
    } on DioException catch (error) {
      if (_isEndpointMissing(error)) {
        throw const QueueServiceUnavailable();
      }
      throw _mapReservationError(error);
    }
  }

  /// Whether the failure means "this API isn't deployed yet" as opposed
  /// to "the request failed".
  ///
  /// Narrow on purpose: only a **404** (no such route) or a **501**
  /// (explicitly not implemented). An offline device, a timeout, a 401,
  /// or a 500 must surface as a real error — quietly showing sample
  /// waiting times to someone whose network is down would send them to
  /// a clinic on invented information.
  bool _isEndpointMissing(DioException error) {
    final int? status = error.response?.statusCode;
    return status == 404 || status == 501;
  }

  /// Turns the status codes a reservation call can return into precise
  /// Arabic, so a refusal explains itself.
  NetworkException _mapReservationError(DioException error) {
    final NetworkException fallback = NetworkException.fromDioException(error);
    final String? message = switch (error.response?.statusCode) {
      403 => 'لا تملك صلاحية إدارة هذا الحجز.',
      409 => 'لديك دور محجوز بالفعل في هذه العيادة.',
      410 => 'انتهت صلاحية هذا الحجز.',
      422 => 'هذه العيادة لا تستقبل حجوزات حالياً.',
      _ => null,
    };

    if (message == null) return fallback;
    return NetworkException(
      message,
      statusCode: fallback.statusCode,
      technicalDetail: fallback.technicalDetail,
    );
  }
}
