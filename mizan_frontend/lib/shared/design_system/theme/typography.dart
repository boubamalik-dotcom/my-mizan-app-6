import 'package:flutter/material.dart';

import 'color_scheme.dart';

/// The Mizan design system's text styles.
///
/// Built on top of Material 3's default [TextTheme] (which already
/// ships sensible Arabic-script-safe font metrics via Flutter's
/// platform default font) rather than a custom font family, so RTL
/// Arabic text always renders with correct shaping/kerning without
/// bundling extra font assets.
class MizanTypography {
  const MizanTypography._();

  static TextTheme textTheme(ColorScheme scheme) {
    final TextTheme base =
        ThemeData(colorScheme: scheme, useMaterial3: true).textTheme;

    return base.copyWith(
      headlineMedium: base.headlineMedium?.copyWith(
        fontWeight: FontWeight.w700,
        color: MizanColors.navy,
      ),
      headlineSmall: base.headlineSmall?.copyWith(
        fontWeight: FontWeight.w700,
        color: MizanColors.navy,
      ),
      titleLarge: base.titleLarge?.copyWith(
        fontWeight: FontWeight.w700,
        color: MizanColors.navy,
      ),
      titleMedium: base.titleMedium?.copyWith(
        fontWeight: FontWeight.w600,
        color: MizanColors.navy,
      ),
      bodyLarge: base.bodyLarge?.copyWith(color: MizanColors.navy),
      bodyMedium: base.bodyMedium?.copyWith(color: MizanColors.textSecondary),
      labelLarge: base.labelLarge?.copyWith(fontWeight: FontWeight.w700),
    );
  }
}
