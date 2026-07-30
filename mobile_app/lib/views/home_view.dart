import 'package:flutter/material.dart';
import 'package:el_mizan_real_estate/services/api_service.dart';

/// الشاشة الرئيسية لتطبيق الميزان العقاري
class HomeView extends StatefulWidget {
  const HomeView({super.key});

  @override
  State<HomeView> createState() => _HomeViewState();
}

class _HomeViewState extends State<HomeView> {
  final ApiService _apiService = ApiService();
  String _status = 'جاري التحقق من الاتصال...';
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _checkHealth();
  }

  Future<void> _checkHealth() async {
    try {
      final result = await _apiService.healthCheck();
      setState(() {
        _status = result['status'] == 'ok'
            ? 'الخادم متصل — منطق الميزان جاهز'
            : 'حالة الخادم: ${result['status']}';
        _loading = false;
      });
    } catch (_) {
      setState(() {
        _status = 'تعذّر الاتصال بالخادم';
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('El Mizan Real Estate'),
        centerTitle: true,
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                'الميزان العقاري',
                style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: const Color(0xFF1B4D3E),
                    ),
              ),
              const SizedBox(height: 8),
              Text(
                'وسيط ذكي لمدينة وهران',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 32),
              if (_loading)
                const CircularProgressIndicator()
              else
                Text(
                  _status,
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyLarge,
                ),
              const SizedBox(height: 24),
              FilledButton(
                onPressed: () {
                  setState(() => _loading = true);
                  _checkHealth();
                },
                child: const Text('إعادة التحقق'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
