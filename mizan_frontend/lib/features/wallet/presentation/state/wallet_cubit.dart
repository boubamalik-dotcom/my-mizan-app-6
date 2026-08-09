import 'package:flutter_bloc/flutter_bloc.dart';

import '../../../../shared/exceptions/app_exception.dart';
import '../../data/wallet_model.dart';
import '../../data/wallet_repository.dart';
import 'wallet_state.dart';

/// Drives the Wallet half of the dashboard's Fulcrum Card.
///
/// A [Cubit] rather than a full `Bloc`: this feature currently does
/// exactly one thing (load the wallet, with retry), so there is no
/// event stream worth naming separately from the method that
/// triggers it. `HostDashboardPage` creates one per dashboard visit
/// via `BlocProvider(create: (_) => WalletCubit()..loadWalletData())`,
/// and only the small `BlocBuilder<WalletCubit, WalletState>` around
/// the balance figure (`WalletBalanceView`) ever rebuilds when it
/// emits — never the rest of the Fulcrum Card, the Chat half, or the
/// dashboard below it.
class WalletCubit extends Cubit<WalletState> {
  WalletCubit({WalletRepository? repository})
      : _repository = repository ?? WalletRepository.instance,
        super(const WalletInitial());

  final WalletRepository _repository;

  /// Fetches (auto-provisioning if necessary) the authenticated
  /// user's wallet. Safe to call more than once — e.g. the user
  /// tapping a [WalletError] to retry — since it always starts by
  /// re-emitting [WalletLoading].
  Future<void> loadWalletData() async {
    emit(const WalletLoading());
    try {
      final WalletModel wallet = await _repository.getOrCreateWallet();
      if (!isClosed) emit(WalletLoaded(wallet));
    } on AppException catch (error) {
      if (!isClosed) emit(WalletError(error.message));
    } catch (_) {
      // Defensive fallback for anything not already an `AppException`
      // (e.g. a malformed response body) — the UI must never be left
      // stuck on `WalletLoading` because of an unanticipated error.
      if (!isClosed) {
        emit(const WalletError('حدث خطأ غير متوقع أثناء تحميل المحفظة.'));
      }
    }
  }

  /// Credits the wallet by [amount].
  Future<void> deposit(double amount) {
    return _runOperation(
      WalletOperation.deposit,
      (WalletModel wallet) => _repository.deposit(
        walletId: wallet.walletId,
        amount: amount,
      ),
    );
  }

  /// Debits the wallet by [amount].
  Future<void> withdraw(double amount) {
    return _runOperation(
      WalletOperation.withdraw,
      (WalletModel wallet) => _repository.withdraw(
        walletId: wallet.walletId,
        amount: amount,
      ),
    );
  }

  /// Sends [amount] from this wallet to [destinationWalletId].
  ///
  /// The destination is a **wallet id**, not a user id or email — the
  /// backend's transfer endpoint performs no user lookup.
  Future<void> transfer({
    required String destinationWalletId,
    required double amount,
  }) {
    return _runOperation(
      WalletOperation.transfer,
      (WalletModel wallet) => _repository.transfer(
        sourceWalletId: wallet.walletId,
        destinationWalletId: destinationWalletId,
        amount: amount,
      ),
    );
  }

  /// Shared shape of every money operation: mark it in flight, run it,
  /// then **re-read the wallet from the server** rather than trusting a
  /// locally-adjusted figure — the backend owns the balance and its
  /// append-only ledger, so a refresh is the only way the UI can be
  /// sure it matches.
  ///
  /// On failure the previous [WalletLoaded] state is restored (so the
  /// balance never vanishes because a transaction was rejected) and the
  /// exception is rethrown, letting the calling sheet keep its form
  /// open and surface the message in a `SnackBar`.
  Future<void> _runOperation(
    WalletOperation operation,
    Future<double> Function(WalletModel wallet) action,
  ) async {
    final WalletState current = state;
    final WalletModel? wallet = switch (current) {
      WalletLoaded(:final wallet) => wallet,
      WalletOperationInProgress(:final wallet) => wallet,
      _ => null,
    };

    if (wallet == null) {
      // Nothing to operate on yet (still loading, or the initial load
      // failed): surface it the same way a rejected transaction is,
      // and leave the current state untouched.
      throw const WalletOperationUnavailable();
    }

    emit(WalletOperationInProgress(wallet: wallet, operation: operation));

    try {
      await action(wallet);
    } on AppException {
      if (!isClosed) emit(WalletLoaded(wallet));
      rethrow;
    } catch (error, stackTrace) {
      if (!isClosed) emit(WalletLoaded(wallet));
      Error.throwWithStackTrace(
        const WalletOperationFailed(),
        stackTrace,
      );
    }

    await loadWalletData();
  }
}

/// Thrown when an operation is requested before the wallet has loaded.
class WalletOperationUnavailable extends AppException {
  const WalletOperationUnavailable()
      : super('لم يتم تحميل المحفظة بعد. يرجى المحاولة بعد لحظات.');
}

/// Thrown for an unexpected (non-[AppException]) operation failure, so
/// the UI still has a display-ready Arabic message to show.
class WalletOperationFailed extends AppException {
  const WalletOperationFailed()
      : super('تعذّر إتمام العملية. يرجى المحاولة مرة أخرى.');
}
