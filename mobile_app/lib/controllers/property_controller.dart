import 'package:el_mizan_real_estate/models/property.dart';
import 'package:el_mizan_real_estate/services/api_service.dart';

/// متحكم العقارات — منطق الميزان لمدينة وهران
class PropertyController {
  PropertyController({ApiService? apiService})
      : _apiService = apiService ?? ApiService();

  final ApiService _apiService;
  List<Property> properties = [];
  bool isLoading = false;
  String? error;

  Future<void> loadProperties() async {
    isLoading = true;
    error = null;
    try {
      properties = await _apiService.fetchProperties();
    } catch (e) {
      error = e.toString();
      properties = [];
    } finally {
      isLoading = false;
    }
  }
}
