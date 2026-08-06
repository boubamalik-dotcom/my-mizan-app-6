import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../config/constants.dart';
import '../models/queue_entry.dart';
import '../providers/patient_session_provider.dart';
import '../providers/queue_controller.dart';
import '../widgets/connection_status_chip.dart';
import '../widgets/turn_alert_banner.dart';
import 'clinic_select_screen.dart';

class QueueStatusScreen extends ConsumerWidget {
  final String clinicId;
  final String patientId;

  const QueueStatusScreen({super.key, required this.clinicId, required this.patientId});

  Future<void> _leaveQueue(BuildContext context, WidgetRef ref) async {
    await ref.read(patientSessionProvider.notifier).clearActiveQueue();
    if (!context.mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const ClinicSelectScreen()),
      (route) => false,
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final queueState = ref.watch(queueControllerProvider(clinicId));
    final queue = queueState.queue;

    QueueEntry? myEntry;
    for (final entry in queue) {
      if (entry.patientId == patientId) {
        myEntry = entry;
        break;
      }
    }

    final currentlyServing = queue
        .where((e) => e.status == QueueStatus.inConsultation)
        .cast<QueueEntry?>()
        .firstWhere((_) => true, orElse: () => null);

    final myIndex = myEntry == null ? -1 : queue.indexOf(myEntry);
    final patientsAhead = myIndex < 0
        ? 0
        : queue.sublist(0, myIndex).where((e) => e.status == QueueStatus.waiting).length;

    final visitComplete = myEntry == null && queueState.loading == false;

    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        title: const Text('Your Queue Status'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 8),
            child: Center(child: ConnectionStatusChip(status: queueState.connectionStatus)),
          ),
          IconButton(
            tooltip: 'Leave',
            icon: const Icon(Icons.logout),
            onPressed: () => _leaveQueue(context, ref),
          ),
        ],
      ),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: () => ref.read(queueControllerProvider(clinicId).notifier).refresh(),
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              if (queueState.error != null) ...[
                Container(
                  padding: const EdgeInsets.all(12),
                  margin: const EdgeInsets.only(bottom: 16),
                  decoration: BoxDecoration(
                    color: Colors.red.shade50,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(queueState.error!, style: TextStyle(color: Colors.red.shade700)),
                ),
              ],
              if (visitComplete)
                _VisitCompleteCard(onDone: () => _leaveQueue(context, ref))
              else ...[
                if (myEntry != null && myEntry.status == QueueStatus.inConsultation)
                  TurnAlertBanner.yourTurn()
                else if (myEntry != null &&
                    myEntry.status == QueueStatus.waiting &&
                    patientsAhead <= nearTurnThreshold)
                  TurnAlertBanner.nearTurn(patientsAhead),
                Row(
                  children: [
                    Expanded(
                      child: _StatCard(
                        label: 'Your number',
                        value: myEntry != null ? '#${myEntry.queueNumber}' : '—',
                        color: Colors.teal,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: _StatCard(
                        label: 'Currently serving',
                        value: currentlyServing != null ? '#${currentlyServing.queueNumber}' : '—',
                        color: Colors.blueGrey,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                if (myEntry != null) ...[
                  Card(
                    elevation: 0,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14),
                      side: BorderSide(color: Colors.grey.shade200),
                    ),
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Text(
                                myEntry.patient.name,
                                style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                              ),
                              if (myEntry.isUrgent) ...[
                                const SizedBox(width: 8),
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                                  decoration: BoxDecoration(
                                    color: Colors.red.shade50,
                                    borderRadius: BorderRadius.circular(999),
                                  ),
                                  child: Text(
                                    'Urgent',
                                    style: TextStyle(
                                        color: Colors.red.shade700,
                                        fontSize: 11,
                                        fontWeight: FontWeight.w700),
                                  ),
                                ),
                              ],
                            ],
                          ),
                          const SizedBox(height: 6),
                          Text(
                            _statusLabel(myEntry.status),
                            style: TextStyle(
                              color: myEntry.status == QueueStatus.inConsultation
                                  ? Colors.green.shade700
                                  : Colors.grey.shade700,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          if (myEntry.status == QueueStatus.waiting) ...[
                            const SizedBox(height: 4),
                            Text(
                              patientsAhead == 0
                                  ? "You're next in line."
                                  : '$patientsAhead patient${patientsAhead == 1 ? '' : 's'} ahead of you.',
                              style: TextStyle(color: Colors.grey.shade600),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ),
                ] else if (queueState.loading)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 40),
                    child: Center(child: CircularProgressIndicator()),
                  ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  String _statusLabel(QueueStatus status) {
    switch (status) {
      case QueueStatus.waiting:
        return 'Waiting';
      case QueueStatus.inConsultation:
        return 'In consultation';
      case QueueStatus.completed:
        return 'Completed';
      case QueueStatus.cancelled:
        return 'Cancelled';
    }
  }
}

class _StatCard extends StatelessWidget {
  final String label;
  final String value;
  final MaterialColor color;

  const _StatCard({required this.label, required this.value, required this.color});

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: Colors.grey.shade200),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: TextStyle(color: Colors.grey.shade600, fontSize: 13)),
            const SizedBox(height: 6),
            Text(
              value,
              style: TextStyle(fontSize: 30, fontWeight: FontWeight.bold, color: color.shade700),
            ),
          ],
        ),
      ),
    );
  }
}

class _VisitCompleteCard extends StatelessWidget {
  final VoidCallback onDone;

  const _VisitCompleteCard({required this.onDone});

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: Colors.grey.shade200),
      ),
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            Icon(Icons.celebration, color: Colors.teal.shade600, size: 40),
            const SizedBox(height: 12),
            const Text(
              'Your visit is complete. Thank you for using Mizan Door!',
              textAlign: TextAlign.center,
              style: TextStyle(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 16),
            FilledButton(onPressed: onDone, child: const Text('Join another queue')),
          ],
        ),
      ),
    );
  }
}
