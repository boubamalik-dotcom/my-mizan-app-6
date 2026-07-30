import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:el_mizan_real_estate/models/property.dart';

/// خدمة التواصل مع واجهة El Mizan Real Estate API
class ApiService {
  ApiService({this.baseUrl = 'http://10.0.2.2:8000'});

  final String baseUrl;

  Future<Map<String, dynamic>> healthCheck() async {
    final response = await http.get(Uri.parse('$baseUrl/health'));
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw Exception('Health check failed: ${response.statusCode}');
  }

  Future<List<Property>> fetchProperties() async {
    final response = await http.get(Uri.parse('$baseUrl/api/v1/properties'));
    if (response.statusCode == 200) {
      final List<dynamic> data = jsonDecode(response.body) as List<dynamic>;
      return data
          .map((item) => Property.fromJson(item as Map<String, dynamic>))
          .toList();
    }
    // Endpoint not implemented yet — return empty list for scaffolding
    if (response.statusCode == 404) {
      return [];
    }
    throw Exception('Failed to load properties: ${response.statusCode}');
  }
}
