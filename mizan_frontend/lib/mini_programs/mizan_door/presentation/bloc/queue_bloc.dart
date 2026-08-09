import 'dart:async';

import 'package:flutter_bloc/flutter_bloc.dart';

import '../../../../shared/exceptions/app_exception.dart';
import '../../data/datasources/queue_socket_data_source.dart';
import '../../data/repositories/queue_repository_impl.dart';
import '../../domain/entities/clinic_queue.dart';
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

  /// Live subscriptions, one per clinic on screen, keyed by clinic id.
  final Map<String, StreamSubscription<ClinicQueueUpdate>> _liveUpdates =
      <String, StreamSubscription<ClinicQueueUpdate>>{};

  /// A refresh of the caller's own reservation, debounced so a burst of
  /// socket frames causes one read rather than one per frame.
  Timer? _reservationRefresh;

  /// How many clinics this screen will hold a live socket to at once.
  ///
  /// One socket per clinic is what the server's per-clinic channels
  /// imply, and it is comfortable at the handful of clinics this app
  /// lists. A deployment with hundreds would want the server to
  /// multiplex instead; capping here means that deployment degrades to
  /// pull-to-refresh for the overflow rather than opening a socket
  /// storm from a phone.
  static const int maxLiveClinics = 12;

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
      // Only once there is something to keep up to date, and never for
      // the bundled showcase catalogue — there is no server behind it
      // to push anything.
      //
      // Guarded separately from the fetch above: live updates are an
      // addition to a queue that has already loaded and been shown, so
      // a failure to subscribe must degrade to pull-to-refresh, never
      // replace a perfectly good queue with an error screen.
      if (!snapshot.isShowcaseData) {
        try {
          _syncLiveUpdates(snapshot.queues);
        } catch (_) {
          // Subscribing failed; the screen stays on the data it has.
        }
      }
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

  // -- Live updates ------------------------------------------------------

  /// Opens a subscription for every clinic now on screen and drops the
  /// ones that are not, so a refresh that changes the list does not
  /// leak sockets for clinics nobody is looking at.
  void _syncLiveUpdates(List<ClinicQueue> queues) {
    final Set<String> wanted = queues
        .take(maxLiveClinics)
        .map((ClinicQueue queue) => queue.clinic.id)
        .toSet();

    for (final String clinicId in _liveUpdates.keys.toList()) {
      if (!wanted.contains(clinicId)) {
        _liveUpdates.remove(clinicId)?.cancel();
      }
    }

    for (final String clinicId in wanted) {
      if (_liveUpdates.containsKey(clinicId)) continue;
      _liveUpdates[clinicId] = _repository
          .watchQueue(clinicId)
          .listen(_applyLiveUpdate, onError: (Object _) {});
    }
  }

  /// Merges one pushed frame into the clinic it belongs to.
  ///
  /// The frame carries figures only — no clinic name, and deliberately
  /// nothing about any patient — so it is merged into the clinic
  /// already on screen rather than replacing it. A frame for a clinic
  /// this screen is not showing is ignored.
  void _applyLiveUpdate(ClinicQueueUpdate update) {
    final QueueState current = state;
    if (current is! QueueLoaded || isClosed) return;

    var matched = false;
    final List<ClinicQueue> merged = current.queues.map((ClinicQueue queue) {
      if (queue.clinic.id != update.clinicId) return queue;
      matched = true;
      return queue.copyWith(
        waitingCount: update.waitingCount,
        averageServiceMinutes: update.averageServiceMinutes,
        isAcceptingPatients: update.isAcceptingPatients,
        nowServingTicket: update.nowServingTicket,
        clearNowServingTicket: update.nowServingTicket == null,
      );
    }).toList(growable: false);

    if (!matched) return;
    emit(current.copyWith(queues: merged));

    // The patient's own position is not in the frame and cannot be
    // derived from it — only the server knows how many active tickets
    // sit below theirs. If they hold a place here, re-read it.
    if (current.reservation?.clinicId == update.clinicId) {
      _scheduleReservationRefresh();
    }
  }

  /// Re-reads the caller's own reservation shortly after a burst of
  /// updates settles.
  ///
  /// Debounced because a clinic advancing several patients quickly
  /// would otherwise trigger a request per frame, and only the last
  /// answer would matter.
  void _scheduleReservationRefresh() {
    _reservationRefresh?.cancel();
    _reservationRefresh = Timer(
      const Duration(milliseconds: 400),
      _refreshReservation,
    );
  }

  Future<void> _refreshReservation() async {
    if (isClosed) return;
    try {
      final QueueSnapshot snapshot = await _repository.fetchQueues();
      final QueueState current = state;
      if (isClosed || current is! QueueLoaded) return;
      emit(
        QueueLoaded(
          queues: snapshot.queues,
          reservation: snapshot.reservation,
          isShowcaseData: snapshot.isShowcaseData,
        ),
      );
    } catch (_) {
      // A failed background refresh leaves the last good state on
      // screen. Replacing a working queue with an error because one
      // opportunistic read failed would be a worse answer than a
      // slightly stale position.
    }
  }

  @override
  Future<void> close() {
    _reservationRefresh?.cancel();
    for (final StreamSubscription<ClinicQueueUpdate> subscription
        in _liveUpdates.values) {
      subscription.cancel();
    }
    _liveUpdates.clear();
    return super.close();
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
