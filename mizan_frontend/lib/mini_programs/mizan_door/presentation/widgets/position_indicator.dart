import 'package:flutter/material.dart';

import '../../../../shared/design_system/constants/app_constants.dart';
import '../../../../shared/design_system/theme/color_scheme.dart';
import '../../domain/entities/queue_reservation.dart';

/// The banner shown when the patient holds a place in a queue.
///
/// Pinned above the clinic list rather than living inside the matching
/// card: "where am I in the queue" is the question this screen exists
/// to answer, and it should not require finding the right card first.
class PositionIndicator extends StatelessWidget {
  const PositionIndicator({
    super.key,
    required this.reservation,
    this.onLeave,
  });

  final QueueReservation reservation;
  final VoidCallback? onLeave;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        borderRadius: AppRadius.cardRadius,
        gradient: const LinearGradient(
          begin: Alignment.topRight,
          end: Alignment.bottomLeft,
          colors: <Color>[MizanColors.navy, MizanColors.navyDark],
        ),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: MizanColors.navy.withOpacity(0.25),
            blurRadius: 18,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const CircleAvatar(
                radius: 16,
                backgroundColor: MizanColors.gold,
                child: Icon(
                  Icons.confirmation_number_outlined,
                  size: 17,
                  color: MizanColors.navy,
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              const Expanded(
                child: Text(
                  'دورك الحالي',
                  style: TextStyle(color: Colors.white70, fontSize: 13),
                ),
              ),
              if (onLeave != null)
                TextButton(
                  onPressed: onLeave,
                  style: TextButton.styleFrom(
                    foregroundColor: MizanColors.goldLight,
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.sm,
                    ),
                  ),
                  child: const Text('إلغاء الدور'),
                ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(
            reservation.isNext
                ? 'أنت التالي'
                : 'يسبقك ${reservation.position} أشخاص',
            style: const TextStyle(
              color: Colors.white,
              fontSize: 26,
              fontWeight: FontWeight.w700,
              height: 1.2,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            reservation.clinicName,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: Colors.white70, fontSize: 13),
          ),
          const SizedBox(height: AppSpacing.sm),
          Row(
            children: <Widget>[
              const Icon(
                Icons.hourglass_bottom_rounded,
                size: 15,
                color: MizanColors.gold,
              ),
              const SizedBox(width: 5),
              Text(
                'الوقت المتوقع: ${reservation.estimatedWaitMinutes} دقيقة',
                style: const TextStyle(
                  color: MizanColors.gold,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
