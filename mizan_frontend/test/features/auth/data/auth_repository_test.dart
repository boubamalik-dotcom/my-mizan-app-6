import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/features/auth/data/auth_repository.dart';
import 'package:mizan_frontend/shared/exceptions/network_exception.dart';
import 'package:mizan_frontend/shared/network/api_client.dart';
import 'package:mizan_frontend/shared/network/endpoints.dart';
import 'package:mizan_frontend/shared/network/token_storage.dart';
import 'package:mocktail/mocktail.dart';

/// [ApiClient] and [TokenStorage] are mocked here (rather than [Dio]
/// itself) so these tests exercise exactly what [AuthRepository] is
/// responsible for — calling the right endpoint with the right body,
/// mapping errors, and persisting the token — without needing to
/// stand up a real [Dio] instance (and its interceptor wiring) or a
/// real network/secure-storage backend.
class MockApiClient extends Mock implements ApiClient {}

class MockTokenStorage extends Mock implements TokenStorage {}

Response<dynamic> _response({required int statusCode, dynamic data}) {
  return Response<dynamic>(
    requestOptions: RequestOptions(path: '/test'),
    statusCode: statusCode,
    data: data,
  );
}

DioException _dioError({required int statusCode, dynamic data}) {
  final RequestOptions requestOptions = RequestOptions(path: '/test');
  return DioException(
    requestOptions: requestOptions,
    type: DioExceptionType.badResponse,
    response: Response<dynamic>(
      requestOptions: requestOptions,
      statusCode: statusCode,
      data: data,
    ),
  );
}

void main() {
  late MockApiClient apiClient;
  late MockTokenStorage tokenStorage;
  late AuthRepository repository;

  setUpAll(() {
    registerFallbackValue(<String, String>{});
  });

  setUp(() {
    apiClient = MockApiClient();
    tokenStorage = MockTokenStorage();
    repository =
        AuthRepository(apiClient: apiClient, tokenStorage: tokenStorage);
  });

  group('register', () {
    test('posts to /auth/register and returns the created user', () async {
      when(() => apiClient.post(ApiEndpoints.register,
          data: any<dynamic>(named: 'data'))).thenAnswer(
        (_) async => _response(
          statusCode: 201,
          data: <String, dynamic>{
            'id': 'user-1',
            'email': 'alice@example.com',
            'full_name': 'Alice Example',
            'is_active': true,
          },
        ),
      );

      final result = await repository.register(
        fullName: 'Alice Example',
        email: 'alice@example.com',
        password: 'correct-horse-battery-staple',
      );

      expect(result.id, 'user-1');
      expect(result.email, 'alice@example.com');
      expect(result.fullName, 'Alice Example');
      expect(result.isActive, isTrue);

      final captured = verify(
        () => apiClient.post(ApiEndpoints.register,
            data: captureAny<dynamic>(named: 'data')),
      ).captured.single as Map<String, dynamic>;
      expect(captured['email'], 'alice@example.com');
      expect(captured['full_name'], 'Alice Example');
      expect(captured['password'], 'correct-horse-battery-staple');
    });

    test('maps a 400 (duplicate email) into a precise Arabic message',
        () async {
      when(() => apiClient.post(ApiEndpoints.register,
          data: any<dynamic>(named: 'data'))).thenThrow(
        _dioError(
          statusCode: 400,
          data: <String, dynamic>{
            'detail': 'User "alice@example.com" already exists.',
          },
        ),
      );

      expect(
        () => repository.register(
          fullName: 'Alice',
          email: 'alice@example.com',
          password: 'correct-horse-battery-staple',
        ),
        throwsA(
          isA<NetworkException>()
              .having((e) => e.statusCode, 'statusCode', 400)
              .having((e) => e.message, 'message', contains('مسجّل بالفعل')),
        ),
      );
    });

    test('falls back to the generic mapping for a non-400 failure', () async {
      when(() => apiClient.post(ApiEndpoints.register,
              data: any<dynamic>(named: 'data')))
          .thenThrow(_dioError(statusCode: 500));

      expect(
        () => repository.register(
          fullName: 'Alice',
          email: 'alice@example.com',
          password: 'correct-horse-battery-staple',
        ),
        throwsA(isA<NetworkException>()
            .having((e) => e.statusCode, 'statusCode', 500)),
      );
    });
  });

  group('login', () {
    test('posts to /auth/login and securely persists the returned token',
        () async {
      when(() => apiClient.post(ApiEndpoints.login,
          data: any<dynamic>(named: 'data'))).thenAnswer(
        (_) async => _response(
          statusCode: 200,
          data: <String, dynamic>{
            'access_token': 'header.payload.signature',
            'token_type': 'bearer',
          },
        ),
      );
      when(() => tokenStorage.saveToken(any())).thenAnswer((_) async {});

      await repository.login(
        email: 'alice@example.com',
        password: 'correct-horse-battery-staple',
      );

      verify(() => tokenStorage.saveToken('header.payload.signature'))
          .called(1);
    });

    test(
        'maps a 401 into a precise Arabic invalid-credentials message and '
        'never persists a token', () async {
      when(() => apiClient.post(ApiEndpoints.login,
          data: any<dynamic>(named: 'data'))).thenThrow(
        _dioError(
          statusCode: 401,
          data: <String, dynamic>{'detail': 'Invalid email or password.'},
        ),
      );

      await expectLater(
        () => repository.login(email: 'alice@example.com', password: 'wrong'),
        throwsA(
          isA<NetworkException>()
              .having((e) => e.statusCode, 'statusCode', 401)
              .having((e) => e.message, 'message', contains('غير صحيحة')),
        ),
      );
      verifyNever(() => tokenStorage.saveToken(any()));
    });
  });

  group('getCurrentUser', () {
    test('fetches /auth/me and returns the profile', () async {
      when(() => apiClient.get(ApiEndpoints.me)).thenAnswer(
        (_) async => _response(
          statusCode: 200,
          data: <String, dynamic>{
            'id': 'user-1',
            'email': 'alice@example.com',
            'full_name': 'Alice Example',
            'is_active': true,
          },
        ),
      );

      final result = await repository.getCurrentUser();
      expect(result.email, 'alice@example.com');
    });
  });

  group('session helpers', () {
    test('isLoggedIn delegates to TokenStorage.hasToken', () async {
      when(() => tokenStorage.hasToken()).thenAnswer((_) async => true);
      expect(await repository.isLoggedIn(), isTrue);
    });

    test('logout clears the stored token', () async {
      when(() => tokenStorage.clearToken()).thenAnswer((_) async {});
      await repository.logout();
      verify(() => tokenStorage.clearToken()).called(1);
    });
  });
}
