import 'package:flutter/material.dart';
import 'package:el_mizan_real_estate/views/home_view.dart';

void main() {
  runApp(const ElMizanApp());
}

/// El Mizan Real Estate — وسيط عقاري ذكي لمدينة وهران
class ElMizanApp extends StatelessWidget {
  const ElMizanApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'El Mizan Real Estate',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF1B4D3E),
          brightness: Brightness.light,
        ),
        useMaterial3: true,
        fontFamily: 'Roboto',
      ),
      home: const HomeView(),
    );
  }
}
