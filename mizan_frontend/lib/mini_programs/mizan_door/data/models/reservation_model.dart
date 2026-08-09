import '../../domain/entities/queue_reservation.dart';
import 'queue_model.dart';

/// Builds [QueueReservation] objects from API payloads.
///
/// Provisional in the same way as [QueueModel]: the endpoint does not
/// exist yet, so this describes the shape the frontend expects.
class ReservationModel {
  const ReservationModel._();

  static QueueReservation fromJson(Map<String, dynamic> json) {
    return QueueReservation(
      id: QueueModel.requireString(json, 'id'),
      clinicId: QueueModel.requireString(json, 'clinic_id'),
      clinicName: json['clinic_name'] as String? ?? '',
      position: QueueModel.requireInt(json, 'position'),
      estimatedWaitMinutes: QueueModel.requireInt(
        json,
        'estimated_wait_minutes',
      ),
      joinedAt: _requireDate(json, 'joined_at'),
      // Absent on a server that predates the consultation stage, which
      // is indistinguishable from "still waiting" and renders the same.
      isInConsultation: json['status'] == 'in_consultation',
    );
  }

  static DateTime _requireDate(Map<String, dynamic> json, String field) {
    final Object? value = json[field];
    if (value is! String) {
      throw FormatException('Expected an ISO-8601 `$field`, got: $value');
    }
    final DateTime? parsed = DateTime.tryParse(value);
    if (parsed == null) {
      throw FormatException('Could not parse `$field` as a date: $value');
    }
    // The backend stores naive UTC timestamps elsewhere in this app
    // (see `ChatMessage`), so a value without an offset is read as UTC
    // rather than as local time.
    return parsed.isUtc
        ? parsed.toLocal()
        : DateTime.utc(
            parsed.year,
            parsed.month,
            parsed.day,
            parsed.hour,
            parsed.minute,
            parsed.second,
            parsed.millisecond,
            parsed.microsecond,
          ).toLocal();
  }
}
