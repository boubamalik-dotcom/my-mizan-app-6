/// Base type for every exception the app's `shared`/`features` layers
/// deliberately throw (as opposed to unexpected framework errors).
///
/// The UI layer only ever needs to know about this one type: any
/// `catch (e)` block can check `e is AppException` and safely show
/// `e.message` directly to the user, regardless of which concrete
/// subclass ([NetworkException], [StorageException], ...) was
/// actually thrown. [message] is always assumed to already be in the
/// app's display language (Arabic) and safe to render as-is — never a
/// raw, untranslated backend or platform error string.
abstract class AppException implements Exception {
  const AppException(this.message);

  /// User-facing, already-localized description of what went wrong.
  final String message;

  @override
  String toString() => message;
}
