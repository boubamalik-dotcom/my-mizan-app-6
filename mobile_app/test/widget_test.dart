import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:el_mizan_real_estate/controllers/property_controller.dart';
import 'package:el_mizan_real_estate/views/home_screen.dart';

void main() {
  testWidgets('Home screen shows El Mizan branding in Arabic RTL', (tester) async {
    await tester.pumpWidget(
      ChangeNotifierProvider(
        create: (_) => PropertyController(),
        child: const MaterialApp(
          home: Directionality(
            textDirection: TextDirection.rtl,
            child: HomeScreen(),
          ),
        ),
      ),
    );

    await tester.pump();
    expect(find.textContaining('El Mizan'), findsWidgets);
    expect(find.textContaining('الميزان العقاري'), findsOneWidget);
  });
}
