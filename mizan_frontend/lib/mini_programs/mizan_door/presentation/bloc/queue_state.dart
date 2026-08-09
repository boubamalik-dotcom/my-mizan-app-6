import '../../domain/entities/clinic_queue.dart';
import '../../domain/entities/queue_reservation.dart';

/// The queue dashboard's state.
///
/// A `sealed` hierarchy like `WalletState` and `PropertyState`, so every
/// `switch` over it is checked for exhaustiveness.
sealed class QueueState {
  const QueueState();
}

/// Queues are being fetched.
class QueueLoading extends QueueState {
  const QueueLoading();
}

/// Queues loaded. An empty [queues] list is a legitimate result — no
/// clinic is running a queue right now — and is what the screen's
/// "لا توجد طوابير نشطة" placeholder renders from.
class QueueLoaded extends QueueState {
  const QueueLoaded({
    required this.queues,
    this.reservation,
    this.isShowcaseData = false,
  });

  final List<ClinicQueue> queues;

  /// The caller's own place in a queue, if they hold one.
  final QueueReservation? reservation;

  /// True when these are the bundled illustrative queues, because the
  /// queue API is not deployed yet.
  final bool isShowcaseData;

  bool get isEmpty => queues.isEmpty;
  bool get hasReservation => reservation != null;

  QueueLoaded copyWith({
    List<ClinicQueue>? queues,
    QueueReservation? reservation,
    bool clearReservation = false,
  }) {
    return QueueLoaded(
      queues: queues ?? this.queues,
      reservation: clearReservation ? null : (reservation ?? this.reservation),
      isShowcaseData: isShowcaseData,
    );
  }
}

/// The queues could not be loaded. [message] is display-ready Arabic.
class QueueError extends QueueState {
  const QueueError(this.message);

  final String message;
}
