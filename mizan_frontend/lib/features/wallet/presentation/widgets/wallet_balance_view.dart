import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
// `intl` exports its own `TextDirection` (for bidi text utilities),
// which collides with Flutter's `dart:ui`/`material.dart` enum of the
// same name used elsewhere in this file — only `NumberFormat` is
// actually needed here, so the clash is avoided entirely rather than
// papering over it with a prefix.
import 'package:intl/intl.dart' show NumberFormat;

import '../../../../shared/design_system/theme/color_scheme.dart';
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

  /// Renders e.g. `15000` as `"15,000"` and `15000.5` as `"15,000.5"`
  /// — grouped thousands, with up to two decimal places only when the
  /// balance actually has a fractional part.
  static final NumberFormat _balanceFormat = NumberFormat('#,##0.##');

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
      WalletLoaded(:final wallet) => Text(
          '${_balanceFormat.format(wallet.balance)} ${wallet.currency}',
          textDirection: TextDirection.ltr,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.w700,
          ),
        ),
      WalletError(:final message) => _RetryableError(message: message),
    };
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
