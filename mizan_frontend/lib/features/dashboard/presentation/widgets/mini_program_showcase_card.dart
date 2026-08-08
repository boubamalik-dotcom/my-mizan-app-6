import 'package:flutter/material.dart';

import '../../../../shared/design_system/constants/app_constants.dart';
import '../../../../shared/design_system/theme/color_scheme.dart';

/// A tappable, white, 16px-rounded showcase card linking to one
/// mini-program from the dashboard.
///
/// Supports two layouts so it can serve both "Scale" sections without
/// duplicating a second widget:
///
///  * [MiniProgramShowcaseCard.wide] — a full-width row (icon beside
///    title/subtitle), used for the single Scale 1 (B2C) entry.
///  * [MiniProgramShowcaseCard.compact] — a vertical layout (icon
///    above title/subtitle), used for the two side-by-side Scale 2
///    (B2B) entries.
///
/// Deliberately styled with only the Mizan brand's navy/gold palette
/// (never a mini-program's own [MiniProgram.accentColor]) so the
/// dashboard's top-level identity stays strictly on-brand; each
/// mini-program's own accent color still applies once it is actually
/// opened.
class MiniProgramShowcaseCard extends StatelessWidget {
  const MiniProgramShowcaseCard.wide({
    super.key,
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.onTap,
  }) : _wide = true;

  const MiniProgramShowcaseCard.compact({
    super.key,
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.onTap,
  }) : _wide = false;

  /// The mini-program's own brand name (kept as-is, e.g. "Mizan
  /// Door" — brand names are not translated).
  final String title;

  /// Short Arabic description of what the mini-program does.
  final String subtitle;

  final IconData icon;
  final VoidCallback onTap;
  final bool _wide;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: MizanColors.surface,
      borderRadius: AppRadius.cardRadius,
      elevation: 3,
      shadowColor: MizanColors.navy.withOpacity(0.08),
      child: InkWell(
        borderRadius: AppRadius.cardRadius,
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: _wide ? _buildWide(context) : _buildCompact(context),
        ),
      ),
    );
  }

  Widget _buildWide(BuildContext context) {
    return Row(
      children: <Widget>[
        _iconBadge(),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(title, style: _titleStyle(context)),
              const SizedBox(height: AppSpacing.xs),
              Text(subtitle, style: _subtitleStyle(context)),
            ],
          ),
        ),
        const Icon(
          Icons.chevron_left_rounded,
          color: MizanColors.textSecondary,
        ),
      ],
    );
  }

  Widget _buildCompact(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        _iconBadge(),
        const SizedBox(height: AppSpacing.sm),
        Text(title, style: _titleStyle(context)),
        const SizedBox(height: AppSpacing.xs),
        Text(
          subtitle,
          style: _subtitleStyle(context),
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
        ),
      ],
    );
  }

  Widget _iconBadge() {
    return CircleAvatar(
      radius: 24,
      backgroundColor: MizanColors.gold.withOpacity(0.15),
      child: Icon(icon, color: MizanColors.gold, size: 24),
    );
  }

  TextStyle? _titleStyle(BuildContext context) {
    return Theme.of(context).textTheme.titleMedium?.copyWith(
          color: MizanColors.navy,
          fontWeight: FontWeight.w700,
        );
  }

  TextStyle? _subtitleStyle(BuildContext context) {
    return Theme.of(context)
        .textTheme
        .bodySmall
        ?.copyWith(color: MizanColors.textSecondary);
  }
}
