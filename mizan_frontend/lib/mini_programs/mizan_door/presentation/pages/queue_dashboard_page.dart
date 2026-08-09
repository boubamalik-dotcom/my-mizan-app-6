import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../../../shared/design_system/constants/app_constants.dart';
import '../../../../shared/design_system/theme/color_scheme.dart';
import '../../../../shared/exceptions/app_exception.dart';
import '../../domain/entities/clinic_queue.dart';
import '../bloc/queue_bloc.dart';
import '../bloc/queue_state.dart';
import '../widgets/position_indicator.dart';
import '../widgets/queue_card.dart';

/// "طابور العيادات" — the Mizan Door mini-program's main screen: live
/// clinic queues and the patient's own place in one.
///
/// Reached two ways, both landing here so the mini-program has a single
/// entry point: the dashboard's Mizan Door card pushes
/// `CoreRoutes.mizanDoor` directly, and
/// `MizanDoorMiniProgram.buildRootWidget` returns this page for anything
/// going through the host shell's mini-program loader.
class QueueDashboardPage extends StatefulWidget {
  const QueueDashboardPage({super.key, QueueDashboardCubit? queueCubit})
      : _cubitOverride = queueCubit;

  /// Injectable for tests, which must not hit the network. In
  /// production a fresh cubit is created and immediately told to
  /// [QueueDashboardCubit.loadQueues].
  final QueueDashboardCubit? _cubitOverride;

  @override
  State<QueueDashboardPage> createState() => _QueueDashboardPageState();
}

class _QueueDashboardPageState extends State<QueueDashboardPage> {
  /// The clinic whose join request is in flight, so only the card that
  /// was pressed shows a spinner rather than the whole list freezing.
  String? _joiningClinicId;

  @override
  Widget build(BuildContext context) {
    return BlocProvider<QueueDashboardCubit>(
      create: (_) =>
          (widget._cubitOverride ?? QueueDashboardCubit())..loadQueues(),
      child: Builder(
        builder: (BuildContext context) => Scaffold(
          backgroundColor: MizanColors.background,
          appBar: AppBar(
            title: const Text('طابور العيادات'),
            leading: IconButton(
              // Points forward in reading order, which under the app's
              // RTL layout is the correct "back" direction.
              icon: const Icon(Icons.arrow_forward_rounded),
              tooltip: 'رجوع',
              onPressed: () => Navigator.of(context).pop(),
            ),
            actions: <Widget>[
              IconButton(
                icon: const Icon(Icons.refresh_rounded),
                tooltip: 'تحديث',
                onPressed: () =>
                    context.read<QueueDashboardCubit>().loadQueues(),
              ),
            ],
          ),
          body: BlocBuilder<QueueDashboardCubit, QueueState>(
            builder: (BuildContext context, QueueState state) {
              return switch (state) {
                QueueLoading() => const _CenteredProgress(),
                QueueError(:final message) => _LoadFailure(message: message),
                QueueLoaded(isEmpty: true) => const _NoActiveQueues(),
                QueueLoaded() => _QueueList(
                    state: state,
                    joiningClinicId: _joiningClinicId,
                    onJoin: (String clinicId) => _join(context, clinicId),
                    onLeave: (String reservationId) =>
                        _leave(context, reservationId),
                  ),
              };
            },
          ),
        ),
      ),
    );
  }

  Future<void> _join(BuildContext context, String clinicId) async {
    // Both resolved before the await: reading them from `context`
    // afterwards would be reaching through a widget tree that may have
    // been torn down while the request was in flight.
    final QueueDashboardCubit cubit = context.read<QueueDashboardCubit>();
    final ScaffoldMessengerState messenger = ScaffoldMessenger.of(context);

    setState(() => _joiningClinicId = clinicId);
    try {
      await cubit.joinQueue(clinicId);
      _notify(messenger, 'تم حجز دورك بنجاح.', isError: false);
    } on AppException catch (error) {
      // Includes `QueueServiceUnavailable`, which is what a
      // not-yet-deployed API produces. Saying so plainly is the point:
      // a reservation is never faked, so the patient must not be left
      // believing they hold one.
      _notify(messenger, error.message, isError: true);
    } catch (_) {
      _notify(messenger, 'تعذّر حجز الدور. يرجى المحاولة مرة أخرى.',
          isError: true);
    } finally {
      if (mounted) setState(() => _joiningClinicId = null);
    }
  }

  Future<void> _leave(BuildContext context, String reservationId) async {
    final QueueDashboardCubit cubit = context.read<QueueDashboardCubit>();
    final ScaffoldMessengerState messenger = ScaffoldMessenger.of(context);

    try {
      await cubit.leaveQueue(reservationId);
      _notify(messenger, 'تم إلغاء دورك.', isError: false);
    } on AppException catch (error) {
      _notify(messenger, error.message, isError: true);
    } catch (_) {
      _notify(messenger, 'تعذّر إلغاء الدور. يرجى المحاولة مرة أخرى.',
          isError: true);
    }
  }

  void _notify(
    ScaffoldMessengerState messenger,
    String message, {
    required bool isError,
  }) {
    if (!mounted) return;
    messenger
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(message),
          backgroundColor: isError ? MizanColors.error : MizanColors.success,
        ),
      );
  }
}

class _QueueList extends StatelessWidget {
  const _QueueList({
    required this.state,
    required this.onJoin,
    required this.onLeave,
    this.joiningClinicId,
  });

  final QueueLoaded state;
  final String? joiningClinicId;
  final void Function(String clinicId) onJoin;
  final void Function(String reservationId) onLeave;

  @override
  Widget build(BuildContext context) {
    final List<ClinicQueue> queues = state.queues;
    final int leadingRows =
        (state.hasReservation ? 1 : 0) + (state.isShowcaseData ? 1 : 0) + 1;

    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.lg,
        AppSpacing.md,
        AppSpacing.lg,
        AppSpacing.xl,
      ),
      itemCount: queues.length + leadingRows,
      itemBuilder: (BuildContext context, int index) {
        int cursor = index;

        if (state.hasReservation) {
          if (cursor == 0) {
            return Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.lg),
              child: PositionIndicator(
                reservation: state.reservation!,
                onLeave: () => onLeave(state.reservation!.id),
              ),
            );
          }
          cursor -= 1;
        }

        if (state.isShowcaseData) {
          if (cursor == 0) return const _ShowcaseNotice();
          cursor -= 1;
        }

        if (cursor == 0) return _SectionHeader(count: queues.length);
        return QueueCard(
          queue: queues[cursor - 1],
          isJoining: joiningClinicId == queues[cursor - 1].clinic.id,
          isCurrentReservation:
              state.reservation?.clinicId == queues[cursor - 1].clinic.id,
          onJoin: () => onJoin(queues[cursor - 1].clinic.id),
        );
      },
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.count});

  final int count;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Row(
        children: <Widget>[
          Text(
            'العيادات المتاحة',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const Spacer(),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
            decoration: BoxDecoration(
              color: MizanColors.navy,
              borderRadius: BorderRadius.circular(AppRadius.card / 2),
            ),
            child: Text(
              '$count',
              style: const TextStyle(
                color: MizanColors.gold,
                fontSize: 12,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Says plainly that these queues are illustrative while the queue API
/// does not exist yet.
///
/// More important here than for a property listing: a wait time is
/// something a patient acts on — leaving home, or not — so invented
/// minutes presented as real would be worse than showing nothing.
class _ShowcaseNotice extends StatelessWidget {
  const _ShowcaseNotice();

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: AppSpacing.md),
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: MizanColors.surface,
        borderRadius: AppRadius.cardRadius,
        border: Border.all(color: MizanColors.gold.withOpacity(0.35)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Icon(Icons.info_outline_rounded,
              size: 18, color: MizanColors.gold),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              'هذه طوابير تجريبية للعرض فقط، ولا تعكس أوقات انتظار حقيقية، '
              'ريثما تصبح خدمة الطوابير متاحة على الخادم.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        ],
      ),
    );
  }
}

class _CenteredProgress extends StatelessWidget {
  const _CenteredProgress();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: CircularProgressIndicator(
        valueColor: AlwaysStoppedAnimation<Color>(MizanColors.gold),
      ),
    );
  }
}

/// Shown when no clinic is running a queue — a legitimate result, not a
/// failure.
class _NoActiveQueues extends StatelessWidget {
  const _NoActiveQueues();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            CircleAvatar(
              radius: 30,
              backgroundColor: MizanColors.gold.withOpacity(0.14),
              child: const Icon(
                Icons.event_busy_outlined,
                color: MizanColors.gold,
                size: 28,
              ),
            ),
            const SizedBox(height: AppSpacing.md),
            Text(
              'لا توجد طوابير نشطة',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(
              'لا تستقبل أي عيادة حجوزات في الوقت الحالي.',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: AppSpacing.md),
            TextButton.icon(
              onPressed: () => context.read<QueueDashboardCubit>().loadQueues(),
              icon: const Icon(Icons.refresh_rounded, size: 18),
              label: const Text('تحديث'),
              style: TextButton.styleFrom(foregroundColor: MizanColors.navy),
            ),
          ],
        ),
      ),
    );
  }
}

class _LoadFailure extends StatelessWidget {
  const _LoadFailure({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            const Icon(Icons.error_outline_rounded,
                color: MizanColors.error, size: 32),
            const SizedBox(height: AppSpacing.md),
            Text(
              message,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: AppSpacing.md),
            FilledButton.icon(
              onPressed: () => context.read<QueueDashboardCubit>().loadQueues(),
              icon: const Icon(Icons.refresh_rounded, size: 18),
              label: const Text('إعادة المحاولة'),
            ),
          ],
        ),
      ),
    );
  }
}
