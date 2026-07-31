import 'dart:convert';

import 'package:http/http.dart' as http;

import 'package:el_mizan_real_estate/models/inspection_booking.dart';
import 'package:el_mizan_real_estate/models/parse_result.dart';
import 'package:el_mizan_real_estate/models/property.dart';

/// خدمة التواصل مع واجهة El Mizan Real Estate API
class ApiService {
  ApiService({this.baseUrl = defaultBaseUrl});

  /// Android emulator → 10.0.2.2 | iOS simulator / desktop → 127.0.0.1
  static const String defaultBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://127.0.0.1:8000',
  );

  final String baseUrl;

  Uri _uri(String path) => Uri.parse('$baseUrl$path');

  Future<Map<String, dynamic>> healthCheck() async {
    final response = await http.get(_uri('/health'));
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw Exception('فشل فحص الاتصال: ${response.statusCode}');
  }

  /// GET /api/v1/properties/ — قائمة عامة مع Privacy Shield
  Future<List<Property>> fetchProperties() async {
    final response = await http.get(_uri('/api/v1/properties/'));
    if (response.statusCode == 200) {
      final List<dynamic> data = jsonDecode(response.body) as List<dynamic>;
      return data
          .map((item) => Property.fromJson(item as Map<String, dynamic>))
          .toList();
    }
    throw Exception('فشل تحميل العقارات: ${response.statusCode}');
  }

  /// POST /api/v1/ai/parse-prompt — فهم الدارجة الوهرانية
  Future<ParseResult> parseBuyerPrompt(String userInput) async {
    final response = await http.post(
      _uri('/api/v1/ai/parse-prompt'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'user_input': userInput}),
    );
    if (response.statusCode == 200) {
      return ParseResult.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>,
      );
    }
    throw Exception('فشل تحليل الطلب: ${response.statusCode}');
  }

  /// POST /api/v1/ai/evaluate-price
  Future<MizanEvaluation> evaluatePrice(Map<String, dynamic> propertyData) async {
    final response = await http.post(
      _uri('/api/v1/ai/evaluate-price'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(propertyData),
    );
    if (response.statusCode == 200) {
      return MizanEvaluation.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>,
      );
    }
    throw Exception('فشل تقييم السعر: ${response.statusCode}');
  }

  /// POST /api/v1/properties/ — إضافة عقار مع تقييم الميزان
  Future<Map<String, dynamic>> createProperty({
    required String title,
    String? description,
    required double price,
    required String address,
    required String district,
    required String documentType,
    required int ownerId,
  }) async {
    final response = await http.post(
      _uri('/api/v1/properties/'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'title': title,
        'description': description,
        'price': price,
        'address': address,
        'district': district,
        'document_type': documentType,
        'owner_id': ownerId,
      }),
    );
    if (response.statusCode == 201 || response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw Exception('فشل إضافة العقار: ${response.statusCode} ${response.body}');
  }

  /// POST /api/v1/inspections/book — حجز معاينة (عمولة 1.5%)
  Future<InspectionBooking> bookInspection({
    required int propertyId,
    required int buyerId,
    required DateTime scheduledAt,
    bool commissionAgreed = true,
  }) async {
    final response = await http.post(
      _uri('/api/v1/inspections/book'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'property_id': propertyId,
        'buyer_id': buyerId,
        'scheduled_at': scheduledAt.toUtc().toIso8601String(),
        'commission_agreed': commissionAgreed,
      }),
    );
    if (response.statusCode == 201 || response.statusCode == 200) {
      return InspectionBooking.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>,
      );
    }
    throw Exception('فشل حجز المعاينة: ${response.statusCode} ${response.body}');
  }
}
