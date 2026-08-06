import 'patient.dart';

enum QueueStatus { waiting, inConsultation, completed, cancelled }

QueueStatus queueStatusFromString(String value) {
  switch (value) {
    case 'waiting':
      return QueueStatus.waiting;
    case 'in_consultation':
      return QueueStatus.inConsultation;
    case 'completed':
      return QueueStatus.completed;
    case 'cancelled':
      return QueueStatus.cancelled;
    default:
      throw ArgumentError('Unknown queue status: $value');
  }
}

class QueueEntry {
  final String id;
  final String clinicId;
  final String patientId;
  final int queueNumber;
  final QueueStatus status;
  final bool isUrgent;
  final DateTime joinedAt;
  final Patient patient;

  const QueueEntry({
    required this.id,
    required this.clinicId,
    required this.patientId,
    required this.queueNumber,
    required this.status,
    required this.isUrgent,
    required this.joinedAt,
    required this.patient,
  });

  factory QueueEntry.fromJson(Map<String, dynamic> json) {
    return QueueEntry(
      id: json['id'] as String,
      clinicId: json['clinic_id'] as String,
      patientId: json['patient_id'] as String,
      queueNumber: json['queue_number'] as int,
      status: queueStatusFromString(json['status'] as String),
      isUrgent: json['is_urgent'] as bool,
      joinedAt: DateTime.parse(json['joined_at'] as String),
      patient: Patient.fromJson(json['patient'] as Map<String, dynamic>),
    );
  }
}

/// Payload broadcast over `WS /ws/clinics/{clinicId}`.
class QueueUpdatedMessage {
  final String clinicId;
  final List<QueueEntry> queue;

  const QueueUpdatedMessage({required this.clinicId, required this.queue});

  factory QueueUpdatedMessage.fromJson(Map<String, dynamic> json) {
    return QueueUpdatedMessage(
      clinicId: json['clinic_id'] as String,
      queue: (json['queue'] as List<dynamic>)
          .map((e) => QueueEntry.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}
