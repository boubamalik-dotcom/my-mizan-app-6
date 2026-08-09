import 'package:flutter/material.dart';

import '../../../../shared/design_system/theme/color_scheme.dart';

/// A small, consistent section title used to introduce each "Scale"
/// of the dashboard (e.g. "خدمات الأفراد والصحة", "الأعمال والأصول").
///
/// Deliberately its own widget — rather than an inline `Text` repeated
/// at every call site — so every section heading on the dashboard
/// stays visually identical as more scales/sections are added later.
class DashboardSectionHeader extends StatelessWidget {
  const DashboardSectionHeader({super.key, required this.title});

  final String title;

  @override
  Widget build(BuildContext context) {
    return Text(
      title,
      style: Theme.of(context).textTheme.titleLarge?.copyWith(
            color: MizanColors.navy,
            fontWeight: FontWeight.w700,
          ),
    );
  }
}
