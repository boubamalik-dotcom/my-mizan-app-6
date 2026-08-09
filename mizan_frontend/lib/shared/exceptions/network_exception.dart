import 'package:dio/dio.dart';

import 'app_exception.dart';

/// Thrown for every failure [ApiClient] surfaces: a non-2xx HTTP
/// response, a timeout, or a connectivity failure.
///
/// [message] is always a ready-to-display Arabic string — callers
/// (repositories, BLoCs, widgets) never need to inspect [statusCode]
/// or parse the backend's response body themselves. [technicalDetail],
/// when present, is the raw `detail` string the backend actually
/// returned; it is deliberately *not* included in [message] (the
/// backend never localizes its error text), but is kept around for
/// logging/debugging.
class NetworkException extends AppException {
  const NetworkException(
    super.message, {
    this.statusCode,
    this.technicalDetail,
  });

  /// The HTTP status code that produced this exception, or `null` for
  /// failures that never reached the server (timeout, no connection).
  final int? statusCode;

  /// The raw, backend-provided `detail` string (English, unlocalized),
  /// kept for logs — never shown to the user directly.
  final String? technicalDetail;

  bool get isUnauthorized => statusCode == 401;
  bool get isForbidden => statusCode == 403;
  bool get isConflict => statusCode == 409;
  bool get isNotFound => statusCode == 404;

  /// Builds a [NetworkException] from a raw [DioException], picking a
  /// sensible Arabic [message] for every failure mode Dio can report.
  factory NetworkException.fromDioException(DioException error) {
    switch (error.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
      case DioExceptionType.transformTimeout:
        return const NetworkException(
          'انتهت مهلة الاتصال بالخادم. يرجى المحاولة مرة أخرى.',
        );
      case DioExceptionType.connectionError:
        return const NetworkException(
          'تعذّر الاتصال بالخادم. يرجى التحقق من اتصالك بالإنترنت.',
        );
      case DioExceptionType.badCertificate:
        return const NetworkException(
          'فشل التحقق من شهادة أمان الخادم.',
        );
      case DioExceptionType.cancel:
        return const NetworkException('تم إلغاء الطلب.');
      case DioExceptionType.badResponse:
        final int? statusCode = error.response?.statusCode;
        final String? detail = _extractDetail(error.response?.data);
        return NetworkException(
          _defaultMessageFor(statusCode),
          statusCode: statusCode,
          technicalDetail: detail,
        );
      case DioExceptionType.unknown:
        return NetworkException(
          'حدث خطأ غير متوقع${error.message != null ? ": ${error.message}" : "."}',
        );
    }
  }

  /// Pulls the backend's `{"detail": ...}` field out of an error
  /// response body. FastAPI reports its own validation errors (422)
  /// as a *list* of `{"loc", "msg", "type"}` objects rather than a
  /// plain string, so both shapes are handled here.
  static String? _extractDetail(dynamic data) {
    if (data is! Map) return null;
    final dynamic detail = data['detail'];
    if (detail is String) return detail;
    if (detail is List && detail.isNotEmpty) {
      final dynamic first = detail.first;
      if (first is Map && first['msg'] is String) {
        return first['msg'] as String;
      }
      return first.toString();
    }
    return null;
  }

  static String _defaultMessageFor(int? statusCode) {
    switch (statusCode) {
      case 400:
        return 'الطلب غير صالح. يرجى التحقق من البيانات المدخلة.';
      case 401:
        return 'بيانات الدخول غير صحيحة أو انتهت صلاحية الجلسة.';
      case 403:
        return 'ليست لديك صلاحية للقيام بهذا الإجراء.';
      case 404:
        return 'العنصر المطلوب غير موجود.';
      case 409:
        return 'يوجد تعارض مع بيانات موجودة بالفعل.';
      case 422:
        return 'البيانات المدخلة غير صالحة. يرجى مراجعتها والمحاولة مرة أخرى.';
      case 423:
        return 'هذا الحساب مقفل مؤقتًا.';
      default:
        if (statusCode != null && statusCode >= 500) {
          return 'حدث خطأ في الخادم. يرجى المحاولة لاحقًا.';
        }
        return 'حدث خطأ غير متوقع. يرجى المحاولة مرة أخرى.';
    }
  }
}
