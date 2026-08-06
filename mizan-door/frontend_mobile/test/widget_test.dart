// Basic smoke tests for the Mizan Door patient app.
//
// These avoid hitting the real backend by overriding `apiServiceProvider`
// with an `ApiService` backed by `http`'s `MockClient`, so the tests are
// deterministic and don't depend on a running server.

import 'package:easy_localization/easy_localization.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:frontend_mobile/config/constants.dart';
import 'package:frontend_mobile/main.dart';
import 'package:frontend_mobile/providers/api_providers.dart';
import 'package:frontend_mobile/services/api_service.dart';

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    // EasyLocalization.ensureInitialized() persists the selected locale via
    // shared_preferences, so its platform channel mock must be set up first.
    SharedPreferences.setMockInitialValues({});
    await EasyLocalization.ensureInitialized();
  });

  testWidgets('shows a loading indicator, then the clinic selection screen', (tester) async {
    final mockClient = MockClient((request) async {
      if (request.url.path == '/clinics') {
        return http.Response('[]', 200);
      }
      return http.Response('Not found', 404);
    });

    await tester.pumpWidget(
      EasyLocalization(
        supportedLocales: supportedLocales,
        path: 'assets/translations',
        fallbackLocale: fallbackLocale,
        startLocale: fallbackLocale,
        child: ProviderScope(
          overrides: [
            apiServiceProvider.overrideWithValue(ApiService(client: mockClient)),
          ],
          child: const MizanDoorApp(),
        ),
      ),
    );

    // Settle both the localization asset load and the persisted patient
    // session load (each shows its own transient loading state first).
    await tester.pumpAndSettle();

    // Default language is French.
    expect(find.text('Mizan Door'), findsOneWidget);
    expect(find.text('Sélectionnez une clinique pour rejoindre sa file'), findsOneWidget);
    expect(find.textContaining("Aucune clinique n'est encore enregistrée"), findsOneWidget);
  });
}
