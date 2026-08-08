/// Central catalog of the `mizan_backend` REST surface this app talks
/// to, so a path never needs to be retyped (and risk drifting from the
/// backend) at every call site.
class ApiEndpoints {
  const ApiEndpoints._();

  /// The backend's base URL, including its `/api/v1` prefix (see
  /// `mizan_backend/main.py`).
  ///
  /// Defaults to the standard Android emulator alias for the host
  /// machine's `localhost` (`10.0.2.2`) during local development.
  /// Override at build time for a real device, iOS simulator, or a
  /// deployed backend, e.g.:
  ///
  /// ```
  /// flutter run --dart-define=API_BASE_URL=https://api.mizan.app/api/v1
  /// ```
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000/api/v1',
  );

  // -- Authentication ---------------------------------------------------

  static const String register = '/auth/register';
  static const String login = '/auth/login';
  static const String me = '/auth/me';
}
