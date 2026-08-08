import 'package:flutter/material.dart';

import '../constants/app_constants.dart';
import 'color_scheme.dart';
import 'typography.dart';

/// The Mizan Super App's single [ThemeData], applied once in
/// `main.dart` so every screen — the host shell, every mini-program,
/// and every feature (starting with auth) — automatically renders
/// with the brand's navy/gold identity, minimalist white cards, and
/// 16px corner radius, without re-declaring any of it locally.
class AppTheme {
  const AppTheme._();

  static ThemeData get light {
    final ColorScheme scheme = mizanColorScheme;

    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: MizanColors.background,
      textTheme: MizanTypography.textTheme(scheme),
      appBarTheme: const AppBarTheme(
        backgroundColor: MizanColors.navy,
        foregroundColor: Colors.white,
        elevation: 0,
        centerTitle: true,
      ),
      cardTheme: CardTheme(
        color: MizanColors.surface,
        elevation: 3,
        margin: EdgeInsets.zero,
        shadowColor: MizanColors.navy.withOpacity(0.08),
        shape: RoundedRectangleBorder(borderRadius: AppRadius.cardRadius),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: MizanColors.background,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.md,
        ),
        labelStyle: const TextStyle(color: MizanColors.textSecondary),
        border: OutlineInputBorder(
          borderRadius: AppRadius.cardRadius,
          borderSide: BorderSide.none,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: AppRadius.cardRadius,
          borderSide: BorderSide(color: Colors.grey.shade300),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: AppRadius.cardRadius,
          borderSide: const BorderSide(color: MizanColors.gold, width: 2),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: AppRadius.cardRadius,
          borderSide: const BorderSide(color: MizanColors.error),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: AppRadius.cardRadius,
          borderSide: const BorderSide(color: MizanColors.error, width: 2),
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: MizanColors.gold,
          foregroundColor: MizanColors.navy,
          disabledBackgroundColor: MizanColors.gold.withOpacity(0.5),
          disabledForegroundColor: MizanColors.navy.withOpacity(0.5),
          minimumSize: const Size.fromHeight(52),
          shape: RoundedRectangleBorder(borderRadius: AppRadius.cardRadius),
          textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: MizanColors.navy,
          textStyle: const TextStyle(fontWeight: FontWeight.w600),
        ),
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: MizanColors.navyDark,
        // Sized explicitly: `contentTextStyle` replaces the default
        // outright rather than merging into it, so omitting a size
        // leaves snackbar text at the text painter's fallback.
        contentTextStyle: const TextStyle(
          color: Colors.white,
          fontSize: 15,
          fontWeight: FontWeight.w600,
        ),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadius.card / 2),
        ),
      ),
    );
  }
}
