import 'package:flutter/material.dart';

import '../../../../shared/design_system/constants/app_constants.dart';
import '../../../../shared/design_system/theme/color_scheme.dart';
import '../../domain/entities/clinic_queue.dart';
import 'wait_time_badge.dart';

/// One clinic's queue: a crisp white card at the Mizan 16px radius,
/// with the wait time in gold and a single action.
class QueueCard extends StatelessWidget {
  const QueueCard({
    super.key,
    required this.queue,
    this.onJoin,
    this.isJoining = false,
    this.isCurrentReservation = false,
  });

  final ClinicQueue queue;
  final VoidCallback? onJoin;

  /// True while this card's own join request is in flight, so only the
  /// button that was pressed shows a spinner.
  final bool isJoining;

  /// True when the patient already holds a place in *this* queue, which
  /// replaces the action with a marker rather than offering to join
  /// twice.
  final bool isCurrentReservation;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: AppSpacing.md),
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: MizanColors.surface,
        borderRadius: AppRadius.cardRadius,
        border: isCurrentReservation
            ? Border.all(color: MizanColors.gold, width: 1.5)
            : null,
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: MizanColors.navy.withOpacity(0.07),
            blurRadius: 14,
            offset: const Offset(0, 5),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              CircleAvatar(
                radius: 20,
                backgroundColor: MizanColors.gold.withOpacity(0.14),
                child: const Icon(
                  Icons.local_hospital_outlined,
                  color: MizanColors.gold,
                  size: 20,
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      queue.clinic.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${queue.clinic.specialty} · ${queue.clinic.district}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          Wrap(
            spacing: AppSpacing.sm,
            runSpacing: AppSpacing.xs,
            children: <Widget>[
              _WaitingCount(count: queue.waitingCount),
              WaitTimeBadge(
                minutes: queue.estimatedWaitMinutes,
                isAccepting: queue.isAcceptingPatients,
              ),
              // Only while someone is actually with the clinician. A
              // permanent "now serving —" placeholder would be noise on
              // the many clinics whose room is empty.
              if (queue.nowServingTicket != null)
                _NowServing(ticket: queue.nowServingTicket!),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          SizedBox(
            width: double.infinity,
            child: _action(context),
          ),
        ],
      ),
    );
  }

  Widget _action(BuildContext context) {
    if (isCurrentReservation) {
      return Container(
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: MizanColors.gold.withOpacity(0.12),
          borderRadius: BorderRadius.circular(AppRadius.card),
        ),
        child: const Text(
          'لديك دور محجوز هنا',
          style: TextStyle(
            color: MizanColors.navy,
            fontWeight: FontWeight.w700,
            fontSize: 13,
          ),
        ),
      );
    }

    if (!queue.isAcceptingPatients) {
      return Container(
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: MizanColors.background,
          borderRadius: BorderRadius.circular(AppRadius.card),
        ),
        child: const Text(
          'لا تستقبل حجوزات حالياً',
          style: TextStyle(
            color: MizanColors.textSecondary,
            fontWeight: FontWeight.w600,
            fontSize: 13,
          ),
        ),
      );
    }

    return FilledButton(
      onPressed: isJoining ? null : onJoin,
      child: isJoining
          ? const SizedBox(
              height: 18,
              width: 18,
              child: CircularProgressIndicator(
                strokeWidth: 2.2,
                valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
              ),
            )
          : const Text('احجز دورك'),
    );
  }
}

/// The ticket currently with the clinician — the "now serving 42" a
/// waiting room displays.
class _NowServing extends StatelessWidget {
  const _NowServing({required this.ticket});

  final int ticket;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: MizanColors.success.withOpacity(0.12),
        borderRadius: BorderRadius.circular(AppRadius.card / 2),
        border: Border.all(color: MizanColors.success.withOpacity(0.4)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          const Icon(
            Icons.meeting_room_outlined,
            size: 14,
            color: MizanColors.success,
          ),
          const SizedBox(width: 5),
          Text(
            'يُخدم الآن رقم $ticket',
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
}

/// How many people are ahead, as a compact figure rather than a
/// sentence — it sits beside the wait time and the two are read
/// together.
class _WaitingCount extends StatelessWidget {
  const _WaitingCount({required this.count});

  final int count;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: MizanColors.navy,
        borderRadius: BorderRadius.circular(AppRadius.card / 2),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          const Icon(Icons.people_alt_outlined,
              size: 14, color: Colors.white70),
          const SizedBox(width: 5),
          Text(
            count == 0 ? 'لا أحد ينتظر' : '$count في الانتظار',
            style: const TextStyle(
              color: Colors.white,
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}
