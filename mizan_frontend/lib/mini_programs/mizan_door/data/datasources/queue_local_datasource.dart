import '../../domain/entities/clinic.dart';
import '../../domain/entities/clinic_queue.dart';

/// A small set of illustrative clinic queues, used while `GET /queues`
/// does not exist in `mizan_backend`.
///
/// Showcase data, not a cache: it exists so the queue screen is usable
/// and reviewable before the API ships. `QueueRepository` reaches for it
/// only when the endpoint is absent, and flags the result so the screen
/// can say plainly that these are illustrative.
///
/// Saying so matters more here than for a property listing. A wait time
/// is something a patient would act on — leaving home, or not — so
/// presenting invented minutes as real would be worse than showing
/// nothing at all.
///
/// The spread is deliberate: a queue that is empty, ones of differing
/// lengths, and one that has stopped admitting patients, so every state
/// the screen can render is reachable without a backend.
class QueueLocalDataSource {
  const QueueLocalDataSource();

  List<ClinicQueue> showcaseQueues() {
    return const <ClinicQueue>[
      ClinicQueue(
        clinic: Clinic(
          id: 'clinic-001',
          name: 'عيادة الأمل للطب العام',
          specialty: 'طب عام',
          district: 'حي الصباح، وهران',
        ),
        waitingCount: 3,
        averageServiceMinutes: 8,
        isAcceptingPatients: true,
      ),
      ClinicQueue(
        clinic: Clinic(
          id: 'clinic-002',
          name: 'مركز النور لطب الأسنان',
          specialty: 'طب الأسنان',
          district: 'وسط المدينة، وهران',
        ),
        waitingCount: 7,
        averageServiceMinutes: 15,
        isAcceptingPatients: true,
      ),
      ClinicQueue(
        clinic: Clinic(
          id: 'clinic-003',
          name: 'عيادة الشفاء للأطفال',
          specialty: 'طب الأطفال',
          district: 'بئر الجير، وهران',
        ),
        waitingCount: 0,
        averageServiceMinutes: 10,
        isAcceptingPatients: true,
      ),
      ClinicQueue(
        clinic: Clinic(
          id: 'clinic-004',
          name: 'مركز الحياة للجلدية',
          specialty: 'الأمراض الجلدية',
          district: 'الصديقية، وهران',
        ),
        waitingCount: 12,
        averageServiceMinutes: 12,
        isAcceptingPatients: false,
      ),
    ];
  }
}
