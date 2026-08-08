import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/shared/network/endpoints.dart';

void main() {
  group('chatHistory', () {
    test('percent-encodes the email in the path', () {
      // An email's `@` is not a legal raw path character.
      expect(
        ApiEndpoints.chatHistory('alice@example.com'),
        '/chat/history/alice%40example.com',
      );
    });
  });

  group('ApiEndpoints.webSocketBaseUrl', () {
    test('swaps the REST scheme for its WebSocket equivalent', () {
      // `baseUrl` is a compile-time constant, so assert the derived
      // form is consistent with it rather than hard-coding a host.
      expect(
        ApiEndpoints.webSocketBaseUrl,
        ApiEndpoints.baseUrl.replaceFirst(RegExp('^http'), 'ws'),
      );
      expect(ApiEndpoints.webSocketBaseUrl, startsWith('ws'));
      expect(ApiEndpoints.webSocketBaseUrl, isNot(startsWith('http')));
    });
  });

  group('ApiEndpoints.chatWebSocket', () {
    test('builds the backend\'s /chat/ws/chat/{client_id} path', () {
      final Uri uri = ApiEndpoints.chatWebSocket(
        clientId: 'alice@example.com',
        roomId: 'general',
        token: 'jwt-token',
      );

      expect(uri.scheme, anyOf('ws', 'wss'));
      // `Uri.path` is the *encoded* path, so the email's `@` appears
      // percent-encoded here — see the dedicated encoding test below.
      expect(uri.path, endsWith('/chat/ws/chat/alice%40example.com'));
    });

    test('percent-encodes the client id so an email is a legal path', () {
      final Uri uri = ApiEndpoints.chatWebSocket(
        clientId: 'alice@example.com',
        roomId: 'general',
        token: 'jwt-token',
      );

      // The raw, un-decoded path must not contain a bare `@`.
      expect(uri.toString(), contains('alice%40example.com'));
      // ...while the decoded segment round-trips to the original email.
      expect(uri.pathSegments.last, 'alice@example.com');
    });

    test('passes room_id and token as query parameters', () {
      final Uri uri = ApiEndpoints.chatWebSocket(
        clientId: 'alice@example.com',
        roomId: 'room-42',
        token: 'header.payload.signature',
      );

      expect(uri.queryParameters['room_id'], 'room-42');
      expect(uri.queryParameters['token'], 'header.payload.signature');
    });
  });
}
