import 'package:flutter/widgets.dart';

/// Standard spacing scale for the Mizan design system, so widgets
/// never hard-code their own ad-hoc padding/gap values.
class AppSpacing {
  const AppSpacing._();

  static const double xs = 4;
  static const double sm = 8;
  static const double md = 16;
  static const double lg = 24;
  static const double xl = 32;
  static const double xxl = 48;
}

/// The Mizan design system's single standard corner radius (per the
/// brand guidelines: 16px), applied uniformly to every card, button,
/// and text field so the app never mixes inconsistent roundness.
class AppRadius {
  const AppRadius._();

  static const double card = 16;
  static final BorderRadius cardRadius = BorderRadius.circular(card);
}
