/// Shared, reusable [FormFieldValidator]-compatible validation
/// functions for the app's forms, so every screen with an email or
/// password field (today: login/register; tomorrow: a profile-edit
/// screen, a "change password" flow, ...) validates them identically
/// instead of each re-implementing its own regex.
class Validators {
  const Validators._();

  /// Matches `mizan_backend`'s use of Pydantic's `EmailStr`: not a
  /// full RFC 5322 implementation, but enough to reject obviously
  /// malformed input client-side before it ever reaches the network.
  static final RegExp _emailPattern = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');

  /// Mirrors `mizan_backend`'s `RegisterRequest.MIN_PASSWORD_LENGTH`
  /// (`src/layer_2_api/auth/auth_schemas.py`) — kept in sync manually,
  /// since the two codebases do not share a schema.
  static const int minPasswordLength = 8;

  static String? required(String? value,
      {String message = 'هذا الحقل مطلوب.'}) {
    if (value == null || value.trim().isEmpty) return message;
    return null;
  }

  static String? email(String? value) {
    final String? requiredError =
        required(value, message: 'البريد الإلكتروني مطلوب.');
    if (requiredError != null) return requiredError;
    if (!_emailPattern.hasMatch(value!.trim())) {
      return 'يرجى إدخال بريد إلكتروني صالح.';
    }
    return null;
  }

  /// For the *login* password field: the backend only requires it be
  /// non-empty (any mismatch with the real password is reported by
  /// the server as an "incorrect email or password" **401**, not a
  /// client-side validation error).
  static String? loginPassword(String? value) {
    return required(value, message: 'كلمة المرور مطلوبة.');
  }

  /// For the *registration* password field: enforces the same
  /// minimum length the backend does, so an obviously-too-short
  /// password is rejected instantly instead of round-tripping to the
  /// server first.
  static String? newPassword(String? value) {
    final String? requiredError =
        required(value, message: 'كلمة المرور مطلوبة.');
    if (requiredError != null) return requiredError;
    if (value!.length < minPasswordLength) {
      return 'يجب ألا تقل كلمة المرور عن $minPasswordLength أحرف.';
    }
    return null;
  }

  static String? fullName(String? value) {
    return required(value, message: 'الاسم الكامل مطلوب.');
  }

  /// For a money amount: must parse as a number and be strictly
  /// positive, mirroring the backend's `gt=0` constraint on every
  /// transaction amount (`wallet_schemas.py`) so an obviously-invalid
  /// figure is caught before it costs a round trip.
  static String? amount(String? value) {
    final String? requiredError = required(value, message: 'المبلغ مطلوب.');
    if (requiredError != null) return requiredError;

    final double? parsed = parseAmount(value!);
    if (parsed == null) return 'يرجى إدخال مبلغ رقمي صالح.';
    if (parsed <= 0) return 'يجب أن يكون المبلغ أكبر من صفر.';
    return null;
  }

  /// Parses a user-entered amount, tolerating surrounding whitespace
  /// and the Arabic decimal separator (`٫`) as well as `.`. Returns
  /// `null` when the text is not a number at all.
  static double? parseAmount(String value) {
    final String normalized = value.trim().replaceAll('٫', '.');
    if (normalized.isEmpty) return null;
    return double.tryParse(normalized);
  }

  /// For the transfer sheet's destination field. The backend expects a
  /// wallet *id* (see `ApiEndpoints.walletTransfer`), so this only
  /// checks that something was entered — the id's existence is the
  /// server's call, surfaced as a **404**.
  static String? walletId(String? value) {
    return required(value, message: 'معرّف المحفظة مطلوب.');
  }
}
