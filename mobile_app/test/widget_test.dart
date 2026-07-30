import 'package:flutter_test/flutter_test.dart';
import 'package:el_mizan_real_estate/main.dart';

void main() {
  testWidgets('El Mizan app loads home screen', (WidgetTester tester) async {
    await tester.pumpWidget(const ElMizanApp());
    expect(find.text('El Mizan Real Estate'), findsOneWidget);
    expect(find.text('الميزان العقاري'), findsOneWidget);
  });
}
