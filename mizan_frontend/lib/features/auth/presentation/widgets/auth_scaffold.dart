import 'package:flutter/material.dart';

import '../../../../shared/design_system/constants/app_constants.dart';
import '../../../../shared/design_system/theme/color_scheme.dart';

/// Shared chrome for every auth screen ([LoginPage], [RegisterPage]):
/// a navy background carrying the "ميزان" brand mark, and a
/// minimalist, 16px-rounded white card holding the screen's own form.
///
/// Kept as one widget so the two screens can never visually drift
/// apart, and so a future auth screen (e.g. "forgot password") gets
/// the same look for free.
class AuthScaffold extends StatelessWidget {
  const AuthScaffold({
    super.key,
    required this.title,
    required this.subtitle,
    required this.child,
  });

  /// Screen headline, e.g. "تسجيل الدخول".
  final String title;

  /// One-line supporting copy shown beneath [title].
  final String subtitle;

  /// The screen's own form/content, rendered inside the white card.
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: MizanColors.navy,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.lg,
              vertical: AppSpacing.xl,
            ),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  const _BrandMark(),
                  const SizedBox(height: AppSpacing.xl),
                  Container(
                    padding: const EdgeInsets.all(AppSpacing.lg),
                    decoration: BoxDecoration(
                      color: MizanColors.surface,
                      borderRadius: AppRadius.cardRadius,
                      boxShadow: <BoxShadow>[
                        BoxShadow(
                          color: MizanColors.navyDark.withOpacity(0.25),
                          blurRadius: 24,
                          offset: const Offset(0, 12),
                        ),
                      ],
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: <Widget>[
                        Text(
                          title,
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.headlineMedium,
                        ),
                        const SizedBox(height: AppSpacing.xs),
                        Text(
                          subtitle,
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.bodyMedium,
                        ),
                        const SizedBox(height: AppSpacing.lg),
                        child,
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _BrandMark extends StatelessWidget {
  const _BrandMark();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: <Widget>[
        Container(
          width: 72,
          height: 72,
          decoration: const BoxDecoration(
            color: MizanColors.gold,
            shape: BoxShape.circle,
          ),
          child: const Icon(
            Icons.balance_rounded,
            color: MizanColors.navy,
            size: 36,
          ),
        ),
        const SizedBox(height: AppSpacing.sm),
        const Text(
          'ميزان',
          style: TextStyle(
            color: Colors.white,
            fontSize: 28,
            fontWeight: FontWeight.bold,
          ),
        ),
      ],
    );
  }
}
