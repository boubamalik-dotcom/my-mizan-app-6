// Basic smoke tests for the Mizan Door patient app.
//
// These avoid hitting the real backend by overriding `apiServiceProvider`
// with an `ApiService` backed by `http`'s `MockClient`, so the tests are
// deterministic and don't depend on a running server.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:frontend_mobile/main.dart';
import 'package:frontend_mobile/providers/api_providers.dart';
import 'package:frontend_mobile/services/api_service.dart';

void main() {
  testWidgets('shows a loading indicator, then the clinic selection screen', (tester) async {
    SharedPreferences.setMockInitialValues({});

    final mockClient = MockClient((request) async {
      if (request.url.path == '/clinics') {
        return http.Response('[]', 200);
      }
      return http.Response('Not found', 404);
    });

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          apiServiceProvider.overrideWithValue(ApiService(client: mockClient)),
        ],
        child: const MizanDoorApp(),
      ),
    );

    // First frame: the persisted patient session hasn't loaded yet.
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    await tester.pumpAndSettle();

    expect(find.text('Mizan Door'), findsOneWidget);
    expect(find.text('Select a clinic to join its queue'), findsOneWidget);
    expect(find.textContaining('No clinics are registered yet'), findsOneWidget);
  });
}
