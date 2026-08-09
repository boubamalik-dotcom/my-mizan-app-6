import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
// `intl` exports its own `TextDirection` (for bidi text utilities),
// which collides with Flutter's `dart:ui`/`material.dart` enum of the
// same name used elsewhere in this file — only `NumberFormat` is
// actually needed here, so the clash is avoided entirely rather than
// papering over it with a prefix.
import 'package:intl/intl.dart' show NumberFormat;

import '../../../../shared/design_system/theme/color_scheme.dart';
import '../../data/wallet_model.dart';
import '../state/wallet_cubit.dart';
import '../state/wallet_state.dart';

/// Maps a [WalletState] to the small widget shown in place of the
/// balance figure on the dashboard's Fulcrum Card.
///
/// This is deliberately the *only* widget wrapped in a
/// `BlocBuilder<WalletCubit, WalletState>` (see `HostDashboardPage`):
/// everything else on the card — the "الرصيد الحالي" caption, the
/// wallet icon, the divider, and the entire Chat half — is built once
/// and never rebuilt just because the wallet finished loading.
class WalletBalanceView extends StatelessWidget {
  const WalletBalanceView({super.key, required this.state});

  final WalletState state;

  static final NumberFormat _balanceFormat = NumberFormat('#,##0.##');

  /// Renders e.g. `15000` as `"15,000"` and `15000.5` as `"15,000.5"`
  /// — grouped thousands, with up to two decimal places only when the
  /// balance actually has a fractional part.
  ///
  /// Exposed so `WalletDetailsPage`'s large balance headline formats
  /// identically to this badge-sized one.
  static String formatBalance(double balance) => _balanceFormat.format(balance);

  @override
  Widget build(BuildContext context) {
    return switch (state) {
      WalletInitial() || WalletLoading() => const SizedBox(
          height: 18,
          width: 18,
          child: CircularProgressIndicator(
            strokeWidth: 2.2,
            valueColor: AlwaysStoppedAnimation<Color>(MizanColors.gold),
          ),
        ),
      WalletLoaded(:final wallet) => _BalanceText(wallet: wallet),
      // A transaction in flight keeps the last known balance on screen,
      // just dimmed: blanking it out mid-transaction would read as the
      // money having vanished.
      WalletOperationInProgress(:final wallet) => Opacity(
          opacity: 0.5,
          child: _BalanceText(wallet: wallet),
        ),
      WalletError(:final message) => _RetryableError(message: message),
    };
  }
}

/// The balance figure itself: grouped thousands plus the wallet's
/// currency code, pinned left-to-right since a number followed by a
/// Latin currency code reads incorrectly if bidi-reordered.
class _BalanceText extends StatelessWidget {
  const _BalanceText({required this.wallet});

  final WalletModel wallet;

  @override
  Widget build(BuildContext context) {
    return Text(
      '${WalletBalanceView.formatBalance(wallet.balance)} ${wallet.currency}',
      textDirection: TextDirection.ltr,
      style: const TextStyle(
        color: Colors.white,
        fontSize: 18,
        fontWeight: FontWeight.w700,
      ),
    );
  }
}

/// "خطأ في التحديث" — tapping it calls [WalletCubit.loadWalletData]
/// again, without requiring the user to leave the dashboard.
class _RetryableError extends StatelessWidget {
  const _RetryableError({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: message,
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: () => context.read<WalletCubit>().loadWalletData(),
        child: const Padding(
          padding: EdgeInsets.symmetric(vertical: 2),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(
                Icons.refresh_rounded,
                color: Colors.white70,
                size: 14,
              ),
              SizedBox(width: 4),
              Text(
                'خطأ في التحديث',
                style: TextStyle(
                  color: Colors.white70,
                  fontSize: 12,
                  decoration: TextDecoration.underline,
                  decorationColor: Colors.white70,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
