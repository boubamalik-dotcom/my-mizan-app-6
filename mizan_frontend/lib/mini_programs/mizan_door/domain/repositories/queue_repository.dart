import '../../data/datasources/queue_socket_data_source.dart';
import '../entities/clinic_queue.dart';
import '../entities/queue_reservation.dart';

/// What a queue lookup returned, and where it came from.
class QueueSnapshot {
  const QueueSnapshot({
    required this.queues,
    required this.reservation,
    required this.isShowcaseData,
  });

  final List<ClinicQueue> queues;

  /// The caller's own place in a queue, if they hold one.
  final QueueReservation? reservation;

  /// True when these are the bundled illustrative queues rather than
  /// live clinic data, because the queue API is not deployed yet. The
  /// screen surfaces this rather than passing sample data off as real
  /// waiting times — which for a medical queue would be worse than
  /// showing nothing.
  final bool isShowcaseData;
}

/// The Mizan Door mini-program's data contract.
///
/// Declared in the domain layer so the presentation layer depends on
/// this rather than on the HTTP implementation, which is what lets the
/// queue cubit be tested without a network at all.
abstract class QueueRepository {
  /// Every clinic queue, plus the caller's own reservation if they hold
  /// one.
  Future<QueueSnapshot> fetchQueues();

  /// Takes a place in `clinicId`'s queue, returning the reservation.
  Future<QueueReservation> joinQueue(String clinicId);

  /// Gives up a reservation.
  Future<void> leaveQueue(String reservationId);

  /// A live stream of `clinicId`'s queue state, for as long as the
  /// subscription is held.
  ///
  /// Reconnects on its own if the socket drops, so a caller never has
  /// to distinguish "nothing has changed" from "the connection died" —
  /// which is the distinction a screen would otherwise get wrong,
  /// showing a frozen number as though it were current.
  ///
  /// The stream carries only the clinic's aggregate figures. A caller
  /// that needs the patient's own position re-reads [fetchQueues],
  /// because the server deliberately never puts a patient on the wire.
  Stream<ClinicQueueUpdate> watchQueue(String clinicId);
}
