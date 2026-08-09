import 'package:flutter/material.dart';

import '../../../../shared/design_system/constants/app_constants.dart';
import '../../../../shared/design_system/theme/color_scheme.dart';

/// A pill showing roughly how long a patient would wait.
///
/// Colour carries the same information as the number, because a wait is
/// the one figure on this screen someone reads at a glance: gold while
/// it is short, amber-ish as it grows, muted once the clinic has
/// stopped admitting people.
class WaitTimeBadge extends StatelessWidget {
  const WaitTimeBadge({
    super.key,
    required this.minutes,
    this.isAccepting = true,
  });

  final int minutes;
  final bool isAccepting;

  /// Minutes past which a wait is presented as long rather than short.
  static const int _longWaitThreshold = 45;

  @override
  Widget build(BuildContext context) {
    final Color accent = !isAccepting
        ? MizanColors.textSecondary
        : minutes >= _longWaitThreshold
            ? MizanColors.error
            : MizanColors.gold;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: accent.withOpacity(0.12),
        borderRadius: BorderRadius.circular(AppRadius.card / 2),
        border: Border.all(color: accent.withOpacity(0.4)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(Icons.schedule_rounded, size: 14, color: accent),
          const SizedBox(width: 5),
          Text(
            _label,
            style: const TextStyle(
              color: MizanColors.navy,
              fontSize: 12,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }

  String get _label {
    if (!isAccepting) return 'مغلق حالياً';
    if (minutes <= 0) return 'بدون انتظار';
    if (minutes < 60) return 'حوالي $minutes دقيقة';

    final int hours = minutes ~/ 60;
    final int remainder = minutes % 60;
    if (remainder == 0) return 'حوالي $hours ساعة';
    return 'حوالي $hours ساعة و$remainder دقيقة';
  }
}
