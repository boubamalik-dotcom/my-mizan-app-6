import 'package:easy_localization/easy_localization.dart';
import 'package:flutter/material.dart';

import '../config/constants.dart';

/// FR/AR language switcher. Selecting Arabic also flips the whole app to
/// RTL automatically, since `MaterialApp.locale` (set from `context.locale`
/// in main.dart) drives Flutter's built-in text-direction resolution.
class LanguageToggle extends StatelessWidget {
  const LanguageToggle({super.key});

  @override
  Widget build(BuildContext context) {
    final currentCode = context.locale.languageCode;

    return Semantics(
      label: 'language.toggle'.tr(),
      container: true,
      child: Container(
        padding: const EdgeInsets.all(2),
        decoration: BoxDecoration(
          border: Border.all(color: Colors.grey.shade300),
          borderRadius: BorderRadius.circular(999),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final locale in supportedLocales)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 1),
                child: _LanguageChip(
                  label: locale.languageCode.toUpperCase(),
                  active: currentCode == locale.languageCode,
                  onTap: () => context.setLocale(locale),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _LanguageChip extends StatelessWidget {
  final String label;
  final bool active;
  final VoidCallback onTap;

  const _LanguageChip({required this.label, required this.active, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(999),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: active ? Colors.teal.shade700 : Colors.transparent,
          borderRadius: BorderRadius.circular(999),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w700,
            color: active ? Colors.white : Colors.grey.shade600,
          ),
        ),
      ),
    );
  }
}
