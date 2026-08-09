/// A snapshot of the authenticated user's Digital Wallet, exactly as
/// returned by `mizan_backend`'s `GET /wallet` / `POST /wallet`
/// (`WalletBalanceResponse` in
/// `layer_2_api/schemas/wallet_schemas.py`).
class WalletModel {
  const WalletModel({
    required this.walletId,
    required this.userId,
    required this.balance,
    required this.currency,
    required this.isLocked,
    required this.version,
  });

  final String walletId;
  final String userId;

  /// The wallet's current balance. The backend serializes its
  /// `Decimal` balance as an exact JSON number; [double] is precise
  /// enough for the *display-only* purpose this model serves here
  /// (see `WalletBalanceView`) — no client-side arithmetic is ever
  /// performed on it.
  final double balance;

  /// Three-letter currency code (e.g. `"DZD"`).
  final String currency;

  final bool isLocked;

  /// Optimistic-concurrency version, echoed back for completeness;
  /// unused by this read-only feature.
  final int version;

  factory WalletModel.fromJson(Map<String, dynamic> json) {
    return WalletModel(
      walletId: json['wallet_id'] as String,
      userId: json['user_id'] as String,
      balance: _asDouble(json['balance']),
      currency: json['currency'] as String,
      isLocked: json['is_locked'] as bool,
      version: json['version'] as int,
    );
  }

  /// Accepts either a JSON number or a numeric string for `balance` —
  /// `dio`'s default JSON decoder always hands back a [num], but this
  /// stays defensive in case a future backend change serializes
  /// `Decimal` as a string instead (a common choice specifically to
  /// avoid floating-point drift).
  static double _asDouble(Object? value) {
    if (value is num) return value.toDouble();
    if (value is String) return double.parse(value);
    throw FormatException('Expected a numeric `balance`, got: $value');
  }

  @override
  String toString() =>
      'WalletModel(walletId: $walletId, balance: $balance $currency)';
}
