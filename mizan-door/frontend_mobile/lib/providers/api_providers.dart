import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/clinic.dart';
import '../services/api_service.dart';

final apiServiceProvider = Provider<ApiService>((ref) => ApiService());

final clinicsProvider = FutureProvider.autoDispose<List<Clinic>>((ref) {
  return ref.watch(apiServiceProvider).listClinics();
});
