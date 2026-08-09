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
    this.isInConsultation = false,
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

  /// Whether the clinic has already called this patient in and they are
  /// with the clinician now.
  ///
  /// Distinct from [isNext], and the distinction matters on screen: a
  /// patient who has been called in is *not* "next", they are being
  /// seen, and telling them to keep waiting would send them back to
  /// their chair.
  final bool isInConsultation;

  /// Whether this patient is at the front of the line but not yet
  /// called in.
  bool get isNext => position == 0 && !isInConsultation;

  @override
  bool operator ==(Object other) => other is QueueReservation && other.id == id;

  @override
  int get hashCode => id.hashCode;
}
