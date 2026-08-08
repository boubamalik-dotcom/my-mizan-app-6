import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/shared/exceptions/network_exception.dart';

DioException _badResponse({required int statusCode, dynamic data}) {
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
  group('NetworkException.fromDioException', () {
    test('extracts a plain string `detail` as technicalDetail', () {
      final NetworkException exception = NetworkException.fromDioException(
        _badResponse(
          statusCode: 400,
          data: <String, dynamic>{'detail': 'Email already registered.'},
        ),
      );

      expect(exception.statusCode, 400);
      expect(exception.technicalDetail, 'Email already registered.');
      expect(exception.message, isNotEmpty);
    });

    test(
        'extracts the first message from a FastAPI-style validation-error '
        'list `detail`', () {
      final NetworkException exception = NetworkException.fromDioException(
        _badResponse(
          statusCode: 422,
          data: <String, dynamic>{
            'detail': <Map<String, dynamic>>[
              <String, dynamic>{
                'loc': <String>['body', 'email'],
                'msg': 'value is not a valid email address',
                'type': 'value_error',
              },
            ],
          },
        ),
      );

      expect(exception.statusCode, 422);
      expect(exception.technicalDetail, 'value is not a valid email address');
    });

    test('falls back to a generic message when `detail` is missing', () {
      final NetworkException exception = NetworkException.fromDioException(
        _badResponse(statusCode: 500, data: null),
      );

      expect(exception.statusCode, 500);
      expect(exception.technicalDetail, isNull);
      expect(exception.message, isNotEmpty);
    });

    test('maps 401/403/404/409 to their matching convenience getters', () {
      expect(
        NetworkException.fromDioException(_badResponse(statusCode: 401))
            .isUnauthorized,
        isTrue,
      );
      expect(
        NetworkException.fromDioException(_badResponse(statusCode: 403))
            .isForbidden,
        isTrue,
      );
      expect(
        NetworkException.fromDioException(_badResponse(statusCode: 404))
            .isNotFound,
        isTrue,
      );
      expect(
        NetworkException.fromDioException(_badResponse(statusCode: 409))
            .isConflict,
        isTrue,
      );
    });

    test('produces a readable message for a connection timeout', () {
      final DioException dioError = DioException(
        requestOptions: RequestOptions(path: '/test'),
        type: DioExceptionType.connectionTimeout,
      );

      final NetworkException exception =
          NetworkException.fromDioException(dioError);

      expect(exception.statusCode, isNull);
      expect(exception.message, isNotEmpty);
    });

    test('produces a readable message for a connection error (offline)', () {
      final DioException dioError = DioException(
        requestOptions: RequestOptions(path: '/test'),
        type: DioExceptionType.connectionError,
      );

      final NetworkException exception =
          NetworkException.fromDioException(dioError);

      expect(exception.statusCode, isNull);
      expect(exception.message, isNotEmpty);
    });
  });
}
