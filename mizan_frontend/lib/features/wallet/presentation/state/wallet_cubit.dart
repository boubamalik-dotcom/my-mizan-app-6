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
      emit(WalletLoaded(wallet));
    } on AppException catch (error) {
      emit(WalletError(error.message));
    } catch (_) {
      // Defensive fallback for anything not already an `AppException`
      // (e.g. a malformed response body) — the UI must never be left
      // stuck on `WalletLoading` because of an unanticipated error.
      emit(const WalletError('حدث خطأ غير متوقع أثناء تحميل المحفظة.'));
    }
  }
}
