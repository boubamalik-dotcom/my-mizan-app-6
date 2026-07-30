import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// ألوان هادئة مستوحاة من بحر وهران والعمارة المتوسطية
class AppColors {
  static const deepSea = Color(0xFF0F3D3E);
  static const lagoon = Color(0xFF1F6F6A);
  static const mist = Color(0xFFE8F1F0);
  static const sand = Color(0xFFF7F3EC);
  static const ink = Color(0xFF1C2B2A);
  static const muted = Color(0xFF5C6F6D);
  static const fair = Color(0xFF2E7D4F);
  static const high = Color(0xFFB45309);
  static const low = Color(0xFF2563EB);
  static const card = Color(0xFFFFFFF8);
}

class AppTheme {
  static ThemeData get light {
    final baseText = GoogleFonts.cairoTextTheme();
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      scaffoldBackgroundColor: AppColors.sand,
      colorScheme: const ColorScheme.light(
        primary: AppColors.deepSea,
        secondary: AppColors.lagoon,
        surface: AppColors.card,
        onPrimary: Colors.white,
        onSecondary: Colors.white,
        onSurface: AppColors.ink,
      ),
      textTheme: baseText.apply(
        bodyColor: AppColors.ink,
        displayColor: AppColors.ink,
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: Colors.transparent,
        elevation: 0,
        centerTitle: true,
        foregroundColor: AppColors.deepSea,
        titleTextStyle: GoogleFonts.cairo(
          fontSize: 20,
          fontWeight: FontWeight.w700,
          color: AppColors.deepSea,
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white.withValues(alpha: 0.92),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: BorderSide.none,
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: AppColors.deepSea,
          foregroundColor: Colors.white,
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          textStyle: GoogleFonts.cairo(fontWeight: FontWeight.w700, fontSize: 16),
        ),
      ),
    );
  }
}

Color mizanBalanceColor(String? balance) {
  switch (balance) {
    case 'عادل':
      return AppColors.fair;
    case 'مرتفع':
      return AppColors.high;
    case 'منخفض':
      return AppColors.low;
    default:
      return AppColors.muted;
  }
}
