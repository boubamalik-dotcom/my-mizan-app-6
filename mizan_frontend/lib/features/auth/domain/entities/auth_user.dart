/// A registered Mizan account's public profile.
///
/// Mirrors `mizan_backend`'s `UserResponse` schema exactly
/// (`src/layer_2_api/auth/auth_schemas.py`) — deliberately never
/// includes a password or password hash, since the backend itself
/// never returns one.
class AuthUser {
  const AuthUser({
    required this.id,
    required this.email,
    required this.fullName,
    required this.isActive,
  });

  /// The account's unique identifier (`UserModel.id`).
  final String id;

  final String email;
  final String fullName;
  final bool isActive;

  factory AuthUser.fromJson(Map<String, dynamic> json) {
    return AuthUser(
      id: json['id'] as String,
      email: json['email'] as String,
      fullName: json['full_name'] as String,
      isActive: json['is_active'] as bool,
    );
  }
}
