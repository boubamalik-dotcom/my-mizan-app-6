import '../../data/wallet_model.dart';

/// The Digital Wallet's finite state machine, driving the balance
/// area of the dashboard's Fulcrum Card (see `WalletBalanceView`).
///
/// Modeled as a `sealed` hierarchy — rather than one class with
/// nullable fields — so every place that switches on a [WalletState]
/// (like `WalletBalanceView.build`) is checked for exhaustiveness by
/// the compiler: adding a new state later is a compile error at every
/// call site that doesn't yet handle it, not a silent runtime gap.
sealed class WalletState {
  const WalletState();
}

/// Before `WalletCubit.loadWalletData()` has ever been called.
class WalletInitial extends WalletState {
  const WalletInitial();
}

/// A fetch (or auto-provisioning) request is in flight.
class WalletLoading extends WalletState {
  const WalletLoading();
}

/// The wallet was fetched (or auto-provisioned) successfully.
class WalletLoaded extends WalletState {
  const WalletLoaded(this.wallet);

  final WalletModel wallet;
}

/// Which money operation is currently in flight — used to label the
/// in-progress UI rather than showing a generic spinner.
enum WalletOperation { deposit, withdraw, transfer }

/// A deposit/withdrawal/transfer is in flight.
///
/// Deliberately carries the last-known [wallet] so the UI can keep the
/// current balance on screen (dimmed, with a progress indicator)
/// instead of blanking it out and making the balance appear to
/// disappear mid-transaction.
class WalletOperationInProgress extends WalletState {
  const WalletOperationInProgress({
    required this.wallet,
    required this.operation,
  });

  final WalletModel wallet;
  final WalletOperation operation;
}

/// The fetch/provisioning attempt failed. [message] is already a
/// ready-to-display Arabic string (see `NetworkException.message`),
/// never a raw exception.
class WalletError extends WalletState {
  const WalletError(this.message);

  final String message;
}
