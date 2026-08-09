import 'clinic.dart';

/// A clinic's queue as it stands right now.
class ClinicQueue {
  const ClinicQueue({
    required this.clinic,
    required this.waitingCount,
    required this.averageServiceMinutes,
    required this.isAcceptingPatients,
  });

  final Clinic clinic;

  /// How many people are ahead in the queue.
  final int waitingCount;

  /// How long the clinic currently takes per patient, which is what
  /// turns a position into a time.
  final int averageServiceMinutes;

  /// False when the clinic has stopped admitting people today — full,
  /// closed, or on a break. The queue is still worth showing so a
  /// patient can see *why* they cannot join.
  final bool isAcceptingPatients;

  /// Roughly how long a patient joining now would wait.
  ///
  /// Derived rather than taken from the server: a position and a
  /// service rate are facts the clinic reports, while the estimate is
  /// arithmetic over them. Computing it here means the number on screen
  /// always agrees with the position shown beside it, even if a
  /// response arrives with the two out of step.
  int get estimatedWaitMinutes => waitingCount * averageServiceMinutes;

  bool get isEmpty => waitingCount == 0;

  @override
  bool operator ==(Object other) =>
      other is ClinicQueue && other.clinic == clinic;

  @override
  int get hashCode => clinic.hashCode;
}
