import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'package:el_mizan_real_estate/theme/app_theme.dart';

class MizanBadge extends StatelessWidget {
  const MizanBadge({super.key, required this.balance});

  final String balance;

  @override
  Widget build(BuildContext context) {
    final color = mizanBalanceColor(balance);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.balance_rounded, size: 16, color: color),
          const SizedBox(width: 4),
          Text(
            'ميزان السعر: $balance',
            style: GoogleFonts.cairo(
              fontSize: 12,
              fontWeight: FontWeight.w700,
              color: color,
            ),
          ),
        ],
      ),
    );
  }
}
