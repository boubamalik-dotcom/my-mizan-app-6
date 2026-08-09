import 'clinic.dart';

/// A clinic's queue as it stands right now.
class ClinicQueue {
  const ClinicQueue({
    required this.clinic,
    required this.waitingCount,
    required this.averageServiceMinutes,
    required this.isAcceptingPatients,
    this.nowServingTicket,
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

  /// The ticket currently with the clinician, or `null` when the room
  /// is free. This is the "now serving 42" figure a waiting room
  /// displays; it is not counted in [waitingCount], which means people
  /// still to be called.
  final int? nowServingTicket;

  /// A copy with the pushed figures replaced, for applying a live
  /// socket update to a clinic already on screen.
  ///
  /// [clearNowServingTicket] exists because `null` cannot otherwise be
  /// distinguished from "leave it as it was", and the room becoming
  /// free is exactly the update that has to be expressible.
  ClinicQueue copyWith({
    int? waitingCount,
    int? averageServiceMinutes,
    bool? isAcceptingPatients,
    int? nowServingTicket,
    bool clearNowServingTicket = false,
  }) {
    return ClinicQueue(
      clinic: clinic,
      waitingCount: waitingCount ?? this.waitingCount,
      averageServiceMinutes:
          averageServiceMinutes ?? this.averageServiceMinutes,
      isAcceptingPatients: isAcceptingPatients ?? this.isAcceptingPatients,
      nowServingTicket: clearNowServingTicket
          ? null
          : (nowServingTicket ?? this.nowServingTicket),
    );
  }

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
