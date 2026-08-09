/// The signed-in patient's own place in a clinic's queue.
///
/// Distinct from `ClinicQueue`, which describes the queue as a whole:
/// this is the one row in it that belongs to the caller.
class QueueReservation {
  const QueueReservation({
    required this.id,
    required this.clinicId,
    required this.clinicName,
    required this.position,
    required this.estimatedWaitMinutes,
    required this.joinedAt,
  });

  final String id;
  final String clinicId;

  /// Carried alongside the id so the reservation banner can name the
  /// clinic without the screen having to hold the whole queue list.
  final String clinicName;

  /// Places ahead of this patient. `0` means they are next.
  final int position;

  final int estimatedWaitMinutes;
  final DateTime joinedAt;

  bool get isNext => position == 0;

  @override
  bool operator ==(Object other) => other is QueueReservation && other.id == id;

  @override
  int get hashCode => id.hashCode;
}
