import 'package:flutter_bloc/flutter_bloc.dart';

import '../../../../shared/exceptions/app_exception.dart';
import '../../data/repositories/queue_repository_impl.dart';
import '../../domain/repositories/queue_repository.dart';
import 'queue_state.dart';

/// Drives the Mizan Door queue dashboard: loads clinic queues and
/// manages the caller's own place in one.
///
/// A [Cubit] rather than a full `Bloc`, matching `WalletCubit`,
/// `ChatCubit`, and `PropertyListingCubit` — the screen's inputs are
/// "load", "join", and "leave", so there is no event stream worth
/// naming separately from the methods that trigger them. (This file
/// keeps its scaffolded `queue_bloc.dart` name so the mini-program's
/// folder layout is untouched.)
class QueueDashboardCubit extends Cubit<QueueState> {
  QueueDashboardCubit({QueueRepository? repository})
      : _repository = repository ?? QueueRepositoryImpl(),
        super(const QueueLoading());

  final QueueRepository _repository;

  /// Fetches every clinic queue and the caller's reservation.
  ///
  /// Safe to call again to retry after a [QueueError], and used as the
  /// refresh after joining or leaving a queue.
  Future<void> loadQueues() async {
    emit(const QueueLoading());

    try {
      final QueueSnapshot snapshot = await _repository.fetchQueues();
      if (isClosed) return;
      emit(
        QueueLoaded(
          queues: snapshot.queues,
          reservation: snapshot.reservation,
          isShowcaseData: snapshot.isShowcaseData,
        ),
      );
    } on AppException catch (error) {
      if (!isClosed) emit(QueueError(error.message));
    } catch (_) {
      // The screen must never be left on a spinner because of an
      // unanticipated failure.
      if (!isClosed) {
        emit(const QueueError('تعذّر تحميل الطوابير. يرجى المحاولة مرة أخرى.'));
      }
    }
  }

  /// Takes a place in `clinicId`'s queue.
  ///
  /// On success the whole board is re-read rather than the reservation
  /// being slotted in locally: joining changes the queue everyone else
  /// sees too, and a position is worth showing only if it came from the
  /// server.
  ///
  /// Rethrows so the calling screen can surface the reason — including
  /// `QueueServiceUnavailable`, which is what a not-yet-deployed API
  /// produces. A reservation is deliberately never faked.
  Future<void> joinQueue(String clinicId) async {
    await _repository.joinQueue(clinicId);
    await loadQueues();
  }

  /// Gives up the caller's reservation, then refreshes.
  Future<void> leaveQueue(String reservationId) async {
    await _repository.leaveQueue(reservationId);
    await loadQueues();
  }
}
