import 'package:flutter/material.dart';

/// The Mizan Super App's brand palette.
///
/// Every screen (host shell, mini-programs, and — starting with the
/// auth screens — every feature) pulls its colors from here rather
/// than hard-coding hex values, so the brand's navy/gold identity
/// stays consistent and can be re-tuned in exactly one place.
class MizanColors {
  const MizanColors._();

  /// Primary brand color: deep navy blue.
  static const Color navy = Color(0xFF0B1D3A);

  /// A darker navy, used for gradients/shadows against [navy] itself.
  static const Color navyDark = Color(0xFF071227);

  /// Secondary brand color: warm gold, used for primary actions and
  /// accents against the navy background.
  static const Color gold = Color(0xFFD4A017);

  /// A lighter gold, used for hover/pressed states and subtle accents.
  static const Color goldLight = Color(0xFFE9C767);

  /// App-wide scaffold background — an off-white that lets
  /// minimalist white cards ([surface]) still read as distinct
  /// elevated surfaces.
  static const Color background = Color(0xFFF4F5F9);

  /// The color of every card/sheet/dialog surface.
  static const Color surface = Colors.white;

  static const Color error = Color(0xFFD64545);
  static const Color success = Color(0xFF1E8E5A);

  /// Secondary/muted text, e.g. field hints and helper copy.
  static const Color textSecondary = Color(0xFF6B7280);
}

/// The [ColorScheme] every [ThemeData] in the app is built from (see
/// `app_theme.dart`), derived from — then overridden to exactly match
/// — [MizanColors].
final ColorScheme mizanColorScheme = ColorScheme.fromSeed(
  seedColor: MizanColors.navy,
  brightness: Brightness.light,
).copyWith(
  primary: MizanColors.navy,
  onPrimary: Colors.white,
  secondary: MizanColors.gold,
  onSecondary: MizanColors.navy,
  surface: MizanColors.surface,
  onSurface: MizanColors.navy,
  error: MizanColors.error,
  onError: Colors.white,
);
