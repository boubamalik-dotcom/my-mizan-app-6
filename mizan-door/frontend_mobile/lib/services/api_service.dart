import 'dart:convert';
import 'package:http/http.dart' as http;

import '../config/constants.dart';
import '../models/clinic.dart';
import '../models/patient.dart';
import '../models/queue_entry.dart';

class ApiException implements Exception {
  final int statusCode;
  final String message;

  ApiException(this.statusCode, this.message);

  @override
  String toString() => 'ApiException($statusCode): $message';
}

/// Thin wrapper around the Mizan Door REST API.
class ApiService {
  final http.Client _client;

  ApiService({http.Client? client}) : _client = client ?? http.Client();

  Uri _uri(String path) => Uri.parse('$apiBaseUrl$path');

  Map<String, dynamic> _decodeObject(http.Response response) {
    if (response.statusCode >= 400) {
      throw ApiException(response.statusCode, response.body);
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  List<dynamic> _decodeList(http.Response response) {
    if (response.statusCode >= 400) {
      throw ApiException(response.statusCode, response.body);
    }
    return jsonDecode(response.body) as List<dynamic>;
  }

  Future<List<Clinic>> listClinics() async {
    final response = await _client.get(_uri('/clinics'));
    return _decodeList(response)
        .map((e) => Clinic.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Looks up an existing patient by phone. Returns null if none exists
  /// (a fresh 404 from the API, not an error).
  Future<Patient?> findPatientByPhone(String phone) async {
    final response = await _client.get(_uri('/patients/by-phone/$phone'));
    if (response.statusCode == 404) return null;
    return Patient.fromJson(_decodeObject(response));
  }

  Future<Patient> registerPatient({
    required String name,
    required String phone,
  }) async {
    final response = await _client.post(
      _uri('/patients'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'name': name, 'phone': phone}),
    );
    return Patient.fromJson(_decodeObject(response));
  }

  Future<List<QueueEntry>> getClinicQueue(String clinicId) async {
    final response = await _client.get(_uri('/clinics/$clinicId/queue'));
    return _decodeList(response)
        .map((e) => QueueEntry.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<QueueEntry> joinQueue({
    required String clinicId,
    required String patientId,
    required bool isUrgent,
  }) async {
    final response = await _client.post(
      _uri('/clinics/$clinicId/queue'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'patient_id': patientId, 'is_urgent': isUrgent}),
    );
    return QueueEntry.fromJson(_decodeObject(response));
  }
}
