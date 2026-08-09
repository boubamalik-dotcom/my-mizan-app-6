import 'package:flutter/material.dart';

import '../theme/color_scheme.dart';

/// The Mizan design system's primary call-to-action button:
/// full-width, gold-filled, 16px-rounded (via
/// `AppTheme.light.elevatedButtonTheme`), with a built-in loading
/// state so callers never need to juggle a spinner and a disabled
/// state by hand.
class PrimaryButton extends StatelessWidget {
  const PrimaryButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.isLoading = false,
  });

  /// Button text, shown whenever [isLoading] is `false`.
  final String label;

  /// Called on tap. Ignored (button effectively disabled) while
  /// [isLoading] is `true`, or if `null`.
  final VoidCallback? onPressed;

  /// Whether an async action triggered by this button is in flight —
  /// swaps [label] for a spinner and disables further taps.
  final bool isLoading;

  @override
  Widget build(BuildContext context) {
    return ElevatedButton(
      onPressed: isLoading ? null : onPressed,
      child: isLoading
          ? const SizedBox(
              height: 22,
              width: 22,
              child: CircularProgressIndicator(
                strokeWidth: 2.4,
                valueColor: AlwaysStoppedAnimation<Color>(MizanColors.navy),
              ),
            )
          : Text(label),
    );
  }
}
