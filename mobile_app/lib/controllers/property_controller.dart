import 'package:flutter/foundation.dart';

import 'package:el_mizan_real_estate/models/parse_result.dart';
import 'package:el_mizan_real_estate/models/property.dart';
import 'package:el_mizan_real_estate/services/api_service.dart';

/// متحكم العقارات والبحث الذكي — منطق الميزان
class PropertyController extends ChangeNotifier {
  PropertyController({ApiService? apiService})
      : _apiService = apiService ?? ApiService();

  final ApiService _apiService;

  List<Property> _all = [];
  List<Property> properties = [];
  ParseResult? lastParse;
  bool isLoading = false;
  bool isParsing = false;
  String? error;

  Future<void> loadProperties() async {
    isLoading = true;
    error = null;
    notifyListeners();
    try {
      _all = await _apiService.fetchProperties();
      properties = List<Property>.from(_all);
    } catch (e) {
      error = e.toString();
      _all = _demoProperties();
      properties = List<Property>.from(_all);
    } finally {
      isLoading = false;
      notifyListeners();
    }
  }

  Future<ParseResult?> searchByPrompt(String input) async {
    if (input.trim().isEmpty) return null;
    isParsing = true;
    error = null;
    notifyListeners();
    try {
      lastParse = await _apiService.parseBuyerPrompt(input.trim());
      properties = _all.where((p) {
        final districtOk = lastParse!.district == null ||
            p.district.contains(lastParse!.district!) ||
            lastParse!.district!.contains(p.district);
        final priceOk =
            lastParse!.maxPrice == null || p.price <= lastParse!.maxPrice!;
        return districtOk && priceOk;
      }).toList();
      return lastParse;
    } catch (e) {
      error = e.toString();
      return null;
    } finally {
      isParsing = false;
      notifyListeners();
    }
  }

  void clearSearch() {
    lastParse = null;
    properties = List<Property>.from(_all);
    notifyListeners();
  }

  /// بيانات تجريبية عند تعذّر الاتصال بالخادم
  List<Property> _demoProperties() {
    return [
      Property.fromJson({
        'id': 1,
        'title': 'شقة F3 بإطلالة بحرية',
        'description': 'شقة مشرقة قرب الكورنيش، وثائق واضحة.',
        'price': 17500000,
        'district': 'الكورنيش',
        'document_type': 'عقد توثيقي',
        'status': 'available',
        'approximate_location': 'وهران — حي الكورنيش (عنوان تقريبي)',
        'address_hidden': true,
        'owner_contact_hidden': true,
        'mizan_evaluation': {
          'price_balance': 'عادل',
          'asking_price': 17500000,
          'district': 'الكورنيش',
          'district_avg_price': 18000000,
          'deviation_percent': -2.8,
          'reasoning':
              'ميزان السعر قريب من متوسط حي الكورنيش لشقق F3. الانحراف ضمن نطاق السوق.',
          'confidence': 0.72,
          'source': 'mizan_local',
        },
        'privacy_note':
            'درع الخصوصية: العنوان الدقيق ورقم المالك يُكشفان بعد تأكيد المعاينة فقط.',
      }),
      Property.fromJson({
        'id': 2,
        'title': 'F3 في بئر الجير',
        'description': 'قريبة من المرافق، مناسبة للعائلات.',
        'price': 18000000,
        'district': 'بئر الجير',
        'document_type': 'دفتر عقاري',
        'status': 'available',
        'approximate_location': 'وهران — حي بئر الجير (عنوان تقريبي)',
        'address_hidden': true,
        'owner_contact_hidden': true,
        'mizan_evaluation': {
          'price_balance': 'مرتفع',
          'asking_price': 18000000,
          'district': 'بئر الجير',
          'district_avg_price': 11000000,
          'deviation_percent': 63.6,
          'reasoning':
              'السعر أعلى من متوسط بئر الجير. يُنصح بمراجعة السعر أو توضيح المزايا.',
          'confidence': 0.72,
          'source': 'mizan_local',
        },
      }),
      Property.fromJson({
        'id': 3,
        'title': 'شقة قرب إيساتو',
        'description': 'موقع حيوي بالقرب من USTO.',
        'price': 7000000,
        'district': 'USTO',
        'document_type': 'عقد توثيقي',
        'status': 'available',
        'approximate_location': 'وهران — حي USTO (عنوان تقريبي)',
        'address_hidden': true,
        'owner_contact_hidden': true,
        'mizan_evaluation': {
          'price_balance': 'منخفض',
          'asking_price': 7000000,
          'district': 'USTO',
          'district_avg_price': 8500000,
          'deviation_percent': -17.6,
          'reasoning': 'السعر جذاب مقارنة بمتوسط الحي — تحقق من الوثائق والموقع.',
          'confidence': 0.7,
          'source': 'mizan_local',
        },
      }),
    ];
  }
}
