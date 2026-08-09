import 'app_exception.dart';

/// Thrown when reading, writing, or deleting a value in secure,
/// on-device storage (`flutter_secure_storage`) fails — for example
/// because the platform's keychain/keystore is locked or unavailable.
///
/// Rare in practice, but never safe to ignore silently: if the access
/// token cannot be persisted, the user must be told their session may
/// not survive an app restart, rather than silently appearing to
/// succeed.
class StorageException extends AppException {
  const StorageException(super.message, {this.cause});

  /// The original error thrown by the underlying storage plugin, kept
  /// for logging — never shown to the user directly.
  final Object? cause;
}
