import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../exceptions/storage_exception.dart';

/// Secure, on-device persistence for the JWT access token issued by
/// `POST /auth/login`.
///
/// Backed by `flutter_secure_storage` — the iOS Keychain, the Android
/// Keystore-backed `EncryptedSharedPreferences`, and the equivalent
/// secure store on every other supported platform — so the raw token
/// is never written to plain-text shared preferences or disk.
///
/// Deliberately a small, standalone class (rather than living inside
/// [ApiClient] or `AuthInterceptor`) so both can depend on it without
/// depending on each other, avoiding a circular import between
/// `api_client.dart` and `interceptors.dart`.
class TokenStorage {
  TokenStorage({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
            );

  /// App-wide singleton. Every part of the app that needs the token
  /// (the API client's auth interceptor, the auth repository, a
  /// startup "already logged in?" check) shares this one instance, so
  /// there is a single source of truth for the current session.
  static final TokenStorage instance = TokenStorage();

  final FlutterSecureStorage _storage;

  static const String _accessTokenKey = 'mizan.auth.access_token';

  /// Reads the currently stored access token, or `null` if the user
  /// is not logged in.
  Future<String?> readToken() async {
    try {
      final String? token = await _storage.read(key: _accessTokenKey);
      return (token == null || token.isEmpty) ? null : token;
    } catch (error) {
      throw StorageException(
        'تعذّرت قراءة بيانات الجلسة المخزنة على هذا الجهاز.',
        cause: error,
      );
    }
  }

  /// Securely persists [token], overwriting any previously stored
  /// value (e.g. from an earlier session).
  Future<void> saveToken(String token) async {
    try {
      await _storage.write(key: _accessTokenKey, value: token);
    } catch (error) {
      throw StorageException(
        'تعذّر حفظ بيانات الجلسة بأمان على هذا الجهاز.',
        cause: error,
      );
    }
  }

  /// Deletes the stored access token, e.g. on logout or after the
  /// server rejects it as expired/invalid (see `AuthInterceptor`).
  Future<void> clearToken() async {
    try {
      await _storage.delete(key: _accessTokenKey);
    } catch (error) {
      throw StorageException(
        'تعذّر مسح بيانات الجلسة المخزنة على هذا الجهاز.',
        cause: error,
      );
    }
  }

  /// Whether a token is currently stored — a cheap, local proxy for
  /// "is the user logged in?" used to decide the app's start-up route
  /// without a network round trip. The token's *validity* is only
  /// ever confirmed by the backend rejecting/accepting an actual
  /// request; this is purely a fast local hint.
  Future<bool> hasToken() async => (await readToken()) != null;
}
