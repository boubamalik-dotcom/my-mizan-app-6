import '../../domain/entities/clinic.dart';
import '../../domain/entities/clinic_queue.dart';

/// Builds [ClinicQueue] objects from API payloads.
///
/// The queue API does not exist in `mizan_backend` yet, so this mapping
/// is the contract the frontend *expects* rather than one verified
/// against a live endpoint. It is deliberately tolerant — numbers may
/// arrive as JSON numbers or strings, and the clinic may be nested or
/// flattened — so the first real payload is unlikely to break it
/// outright. Re-check it against the real schema when the endpoint
/// lands.
class QueueModel {
  const QueueModel._();

  static ClinicQueue fromJson(Map<String, dynamic> json) {
    final Map<String, dynamic> clinicJson =
        json['clinic'] is Map<String, dynamic>
            ? json['clinic'] as Map<String, dynamic>
            : json;

    return ClinicQueue(
      clinic: Clinic(
        id: requireString(clinicJson, 'id'),
        name: requireString(clinicJson, 'name'),
        specialty: clinicJson['specialty'] as String? ?? 'طب عام',
        district: clinicJson['district'] as String? ?? '',
      ),
      waitingCount: requireInt(json, 'waiting_count'),
      averageServiceMinutes: requireInt(json, 'average_service_minutes'),
      isAcceptingPatients: json['is_accepting_patients'] as bool? ?? true,
      nowServingTicket: json['now_serving_ticket'] is int
          ? json['now_serving_ticket'] as int
          : null,
    );
  }

  static String requireString(Map<String, dynamic> json, String field) {
    final Object? value = json[field];
    if (value is String) return value;
    throw FormatException('Expected a string `$field`, got: $value');
  }

  static int requireInt(Map<String, dynamic> json, String field) {
    final Object? value = json[field];
    if (value is int) return value;
    if (value is num) return value.toInt();
    if (value is String) {
      final int? parsed = int.tryParse(value);
      if (parsed != null) return parsed;
    }
    throw FormatException('Expected an integer `$field`, got: $value');
  }
}
