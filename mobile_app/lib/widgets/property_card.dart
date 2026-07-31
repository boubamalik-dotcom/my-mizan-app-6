import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart' hide TextDirection;

import 'package:el_mizan_real_estate/models/property.dart';
import 'package:el_mizan_real_estate/theme/app_theme.dart';
import 'package:el_mizan_real_estate/widgets/mizan_badge.dart';

class PropertyCard extends StatelessWidget {
  const PropertyCard({
    super.key,
    required this.property,
    required this.onTap,
  });

  final Property property;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final priceFmt = NumberFormat.decimalPattern('ar');
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(22),
        child: Ink(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(22),
            gradient: const LinearGradient(
              begin: Alignment.topRight,
              end: Alignment.bottomLeft,
              colors: [Color(0xFFFFFFF8), Color(0xFFEAF3F2)],
            ),
            boxShadow: [
              BoxShadow(
                color: AppColors.deepSea.withValues(alpha: 0.08),
                blurRadius: 18,
                offset: const Offset(0, 8),
              ),
            ],
            border: Border.all(color: Colors.white.withValues(alpha: 0.7)),
          ),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        property.title,
                        style: GoogleFonts.cairo(
                          fontSize: 17,
                          fontWeight: FontWeight.w800,
                          color: AppColors.ink,
                        ),
                      ),
                    ),
                    MizanBadge(balance: property.priceBalance),
                  ],
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    const Icon(Icons.location_on_outlined,
                        size: 18, color: AppColors.lagoon),
                    const SizedBox(width: 4),
                    Expanded(
                      child: Text(
                        'وهران — ${property.district}',
                        style: GoogleFonts.cairo(
                          fontSize: 14,
                          color: AppColors.muted,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ],
                ),
                if (property.documentType != null) ...[
                  const SizedBox(height: 6),
                  Text(
                    'الوثيقة: ${property.documentType}',
                    style: GoogleFonts.cairo(fontSize: 13, color: AppColors.muted),
                  ),
                ],
                const SizedBox(height: 14),
                Row(
                  children: [
                    Text(
                      '${priceFmt.format(property.price)} دج',
                      style: GoogleFonts.cairo(
                        fontSize: 18,
                        fontWeight: FontWeight.w800,
                        color: AppColors.deepSea,
                      ),
                    ),
                    const Spacer(),
                    Text(
                      'التفاصيل',
                      style: GoogleFonts.cairo(
                        color: AppColors.lagoon,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const Icon(Icons.chevron_left, color: AppColors.lagoon),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
