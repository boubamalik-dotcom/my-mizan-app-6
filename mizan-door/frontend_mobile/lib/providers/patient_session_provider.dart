import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/patient.dart';

/// Locally-persisted state for "who is using this app" and "which queue are
/// they currently tracking". This stands in for a real login/session system,
/// which is out of scope for this MVP (the backend has no patient accounts).
class PatientSession {
  final bool loaded;
  final String? patientId;
  final String? name;
  final String? phone;
  final String? activeClinicId;
  final String? activeQueueEntryId;

  const PatientSession({
    this.loaded = false,
    this.patientId,
    this.name,
    this.phone,
    this.activeClinicId,
    this.activeQueueEntryId,
  });

  bool get isRegistered => patientId != null;
  bool get hasActiveQueue => activeClinicId != null && activeQueueEntryId != null;

  PatientSession copyWith({
    bool? loaded,
    String? patientId,
    String? name,
    String? phone,
    String? activeClinicId,
    String? activeQueueEntryId,
    bool clearActiveQueue = false,
  }) {
    return PatientSession(
      loaded: loaded ?? this.loaded,
      patientId: patientId ?? this.patientId,
      name: name ?? this.name,
      phone: phone ?? this.phone,
      activeClinicId: clearActiveQueue ? null : (activeClinicId ?? this.activeClinicId),
      activeQueueEntryId: clearActiveQueue ? null : (activeQueueEntryId ?? this.activeQueueEntryId),
    );
  }
}

const _kPatientId = 'mizan_door.patient_id';
const _kPatientName = 'mizan_door.patient_name';
const _kPatientPhone = 'mizan_door.patient_phone';
const _kActiveClinicId = 'mizan_door.active_clinic_id';
const _kActiveQueueEntryId = 'mizan_door.active_queue_entry_id';

class PatientSessionController extends Notifier<PatientSession> {
  @override
  PatientSession build() {
    _load();
    return const PatientSession();
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    state = PatientSession(
      loaded: true,
      patientId: prefs.getString(_kPatientId),
      name: prefs.getString(_kPatientName),
      phone: prefs.getString(_kPatientPhone),
      activeClinicId: prefs.getString(_kActiveClinicId),
      activeQueueEntryId: prefs.getString(_kActiveQueueEntryId),
    );
  }

  Future<void> savePatient(Patient patient) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kPatientId, patient.id);
    await prefs.setString(_kPatientName, patient.name);
    await prefs.setString(_kPatientPhone, patient.phone);
    state = state.copyWith(patientId: patient.id, name: patient.name, phone: patient.phone);
  }

  Future<void> setActiveQueue({required String clinicId, required String queueEntryId}) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kActiveClinicId, clinicId);
    await prefs.setString(_kActiveQueueEntryId, queueEntryId);
    state = state.copyWith(activeClinicId: clinicId, activeQueueEntryId: queueEntryId);
  }

  Future<void> clearActiveQueue() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kActiveClinicId);
    await prefs.remove(_kActiveQueueEntryId);
    state = state.copyWith(clearActiveQueue: true);
  }
}

final patientSessionProvider =
    NotifierProvider<PatientSessionController, PatientSession>(PatientSessionController.new);
