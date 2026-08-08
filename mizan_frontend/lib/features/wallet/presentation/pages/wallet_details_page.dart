import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../../../shared/design_system/constants/app_constants.dart';
import '../../../../shared/design_system/theme/color_scheme.dart';
import '../../data/wallet_model.dart';
import '../state/wallet_cubit.dart';
import '../state/wallet_state.dart';
import '../widgets/wallet_action_sheet.dart';
import '../widgets/wallet_balance_view.dart';

/// "المحفظة الرقمية" — the full Wallet screen, reached by tapping the
/// wallet half of the dashboard's Fulcrum Card.
///
/// Owns its own [WalletCubit] (routes go through `CoreNavigator`, which
/// has no handle on the dashboard's instance) and pops `true` if any
/// operation succeeded, so the dashboard knows to refresh its own copy
/// of the balance rather than showing a stale figure on return.
class WalletDetailsPage extends StatefulWidget {
  const WalletDetailsPage({super.key, WalletCubit? walletCubit})
      : _walletCubitOverride = walletCubit;

  /// Injectable for tests, which must not hit the network. In
  /// production a fresh [WalletCubit] is created and immediately told
  /// to [WalletCubit.loadWalletData].
  final WalletCubit? _walletCubitOverride;

  @override
  State<WalletDetailsPage> createState() => _WalletDetailsPageState();
}

class _WalletDetailsPageState extends State<WalletDetailsPage> {
  /// Whether the balance changed while this page was open, which the
  /// dashboard uses to decide if it needs to re-read the wallet.
  bool _didMutateBalance = false;

  @override
  Widget build(BuildContext context) {
    return BlocProvider<WalletCubit>(
      create: (_) =>
          (widget._walletCubitOverride ?? WalletCubit())..loadWalletData(),
      child: Builder(
        builder: (BuildContext context) {
          return Scaffold(
            backgroundColor: MizanColors.background,
            appBar: AppBar(
              title: const Text('المحفظة الرقمية'),
              leading: IconButton(
                // Points *forward* in reading order, which under the
                // app's RTL layout is the correct "back" direction.
                icon: const Icon(Icons.arrow_forward_rounded),
                tooltip: 'رجوع',
                onPressed: () => Navigator.of(context).pop(_didMutateBalance),
              ),
            ),
            body: SafeArea(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(AppSpacing.lg),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    BlocBuilder<WalletCubit, WalletState>(
                      builder: (BuildContext context, WalletState state) =>
                          _BalanceCard(state: state),
                    ),
                    const SizedBox(height: AppSpacing.xl),
                    Text(
                      'العمليات',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: AppSpacing.md),
                    BlocBuilder<WalletCubit, WalletState>(
                      // Only the buttons' enabled state depends on the
                      // wallet, so this rebuild is scoped to the row.
                      builder: (BuildContext context, WalletState state) =>
                          _ActionRow(
                        enabled: state is WalletLoaded,
                        currency: switch (state) {
                          WalletLoaded(:final wallet) => wallet.currency,
                          WalletOperationInProgress(:final wallet) =>
                            wallet.currency,
                          _ => null,
                        },
                        onCompleted: _handleOperationCompleted,
                      ),
                    ),
                    const SizedBox(height: AppSpacing.xl),
                    const _LedgerNote(),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  void _handleOperationCompleted(String successMessage) {
    setState(() => _didMutateBalance = true);
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(successMessage),
          backgroundColor: MizanColors.success,
        ),
      );
  }
}

/// The headline balance: a navy card that keeps the figure prominent
/// and legible, with the wallet's id and lock status underneath.
class _BalanceCard extends StatelessWidget {
  const _BalanceCard({required this.state});

  final WalletState state;

  @override
  Widget build(BuildContext context) {
    final WalletModel? wallet = switch (state) {
      WalletLoaded(:final wallet) => wallet,
      WalletOperationInProgress(:final wallet) => wallet,
      _ => null,
    };
    final bool isBusy = state is WalletLoading ||
        state is WalletInitial ||
        state is WalletOperationInProgress;

    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        borderRadius: AppRadius.cardRadius,
        gradient: const LinearGradient(
          begin: Alignment.topRight,
          end: Alignment.bottomLeft,
          colors: <Color>[MizanColors.navy, MizanColors.navyDark],
        ),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: MizanColors.navy.withOpacity(0.25),
            blurRadius: 20,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const CircleAvatar(
                radius: 18,
                backgroundColor: MizanColors.gold,
                child: Icon(
                  Icons.account_balance_wallet_rounded,
                  color: MizanColors.navy,
                  size: 18,
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              const Expanded(
                child: Text(
                  'الرصيد الحالي',
                  style: TextStyle(color: Colors.white70, fontSize: 13),
                ),
              ),
              if (isBusy)
                const SizedBox(
                  height: 16,
                  width: 16,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    valueColor: AlwaysStoppedAnimation<Color>(
                      MizanColors.gold,
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          if (wallet != null)
            Opacity(
              opacity: state is WalletOperationInProgress ? 0.5 : 1,
              child: Text(
                '${WalletBalanceView.formatBalance(wallet.balance)}'
                ' ${wallet.currency}',
                textDirection: TextDirection.ltr,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 34,
                  fontWeight: FontWeight.w700,
                  height: 1.1,
                ),
              ),
            )
          else if (state is WalletError)
            _BalanceError(message: (state as WalletError).message)
          else
            const Text(
              '— —',
              style: TextStyle(
                color: Colors.white38,
                fontSize: 34,
                fontWeight: FontWeight.w700,
              ),
            ),
          if (wallet != null) ...<Widget>[
            const SizedBox(height: AppSpacing.md),
            Row(
              children: <Widget>[
                Expanded(
                  child: Text(
                    'رقم المحفظة: ${wallet.walletId}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    textDirection: TextDirection.ltr,
                    textAlign: TextAlign.left,
                    style: const TextStyle(
                      color: Colors.white54,
                      fontSize: 11,
                    ),
                  ),
                ),
                if (wallet.isLocked)
                  const Row(
                    children: <Widget>[
                      Icon(Icons.lock_rounded, size: 12, color: Colors.white70),
                      SizedBox(width: 4),
                      Text(
                        'مقفلة',
                        style: TextStyle(color: Colors.white70, fontSize: 11),
                      ),
                    ],
                  ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

class _BalanceError extends StatelessWidget {
  const _BalanceError({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(
          message,
          style: const TextStyle(color: Colors.white, fontSize: 14),
        ),
        const SizedBox(height: AppSpacing.sm),
        TextButton.icon(
          onPressed: () => context.read<WalletCubit>().loadWalletData(),
          icon: const Icon(Icons.refresh_rounded, size: 16),
          label: const Text('إعادة المحاولة'),
          style: TextButton.styleFrom(foregroundColor: MizanColors.gold),
        ),
      ],
    );
  }
}

/// The three symmetrical action buttons. Each occupies exactly the same
/// width via [Expanded], so the row stays balanced under RTL as well.
class _ActionRow extends StatelessWidget {
  const _ActionRow({
    required this.enabled,
    required this.onCompleted,
    this.currency,
  });

  final bool enabled;
  final String? currency;
  final void Function(String successMessage) onCompleted;

  @override
  Widget build(BuildContext context) {
    final WalletCubit cubit = context.read<WalletCubit>();

    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Expanded(
            child: _ActionButton(
              icon: Icons.arrow_downward_rounded,
              label: 'إيداع',
              enabled: enabled,
              onTap: () => _open(
                context,
                title: 'إيداع رصيد',
                icon: Icons.arrow_downward_rounded,
                submit: (WalletActionInput input) =>
                    cubit.deposit(input.amount),
                successMessage: 'تم الإيداع بنجاح.',
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: _ActionButton(
              icon: Icons.arrow_upward_rounded,
              label: 'سحب',
              enabled: enabled,
              onTap: () => _open(
                context,
                title: 'سحب رصيد',
                icon: Icons.arrow_upward_rounded,
                submit: (WalletActionInput input) =>
                    cubit.withdraw(input.amount),
                successMessage: 'تم السحب بنجاح.',
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: _ActionButton(
              icon: Icons.swap_horiz_rounded,
              label: 'تحويل',
              enabled: enabled,
              onTap: () => _open(
                context,
                title: 'تحويل رصيد',
                icon: Icons.swap_horiz_rounded,
                requiresDestination: true,
                submit: (WalletActionInput input) => cubit.transfer(
                  destinationWalletId: input.destinationWalletId!,
                  amount: input.amount,
                ),
                successMessage: 'تم التحويل بنجاح.',
              ),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _open(
    BuildContext context, {
    required String title,
    required IconData icon,
    required WalletActionSubmit submit,
    required String successMessage,
    bool requiresDestination = false,
  }) async {
    final bool succeeded = await WalletActionSheet.show(
      context,
      title: title,
      icon: icon,
      confirmLabel: 'تأكيد',
      requiresDestination: requiresDestination,
      currency: currency,
      onSubmit: submit,
    );
    if (succeeded) onCompleted(successMessage);
  }
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({
    required this.icon,
    required this.label,
    required this.enabled,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final bool enabled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: MizanColors.surface,
      borderRadius: AppRadius.cardRadius,
      elevation: enabled ? 3 : 0,
      shadowColor: MizanColors.navy.withOpacity(0.08),
      child: InkWell(
        borderRadius: AppRadius.cardRadius,
        onTap: enabled ? onTap : null,
        child: Opacity(
          opacity: enabled ? 1 : 0.45,
          child: Padding(
            padding: const EdgeInsets.symmetric(
              vertical: AppSpacing.md,
              horizontal: AppSpacing.sm,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                CircleAvatar(
                  radius: 20,
                  backgroundColor: MizanColors.gold.withOpacity(0.15),
                  child: Icon(icon, color: MizanColors.gold, size: 20),
                ),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  label,
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// A short, honest note about how the backend treats these operations —
/// every one is appended to an immutable ledger, which is why the app
/// re-reads the balance from the server after each action instead of
/// adjusting it locally.
class _LedgerNote extends StatelessWidget {
  const _LedgerNote();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: MizanColors.surface,
        borderRadius: AppRadius.cardRadius,
        border: Border.all(color: MizanColors.gold.withOpacity(0.35)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Icon(
            Icons.verified_user_outlined,
            color: MizanColors.gold,
            size: 18,
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              'تُسجَّل كل عملية في سجل غير قابل للتعديل، ويُقرأ الرصيد من '
              'الخادم بعد كل عملية لضمان تطابقه مع السجل.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        ],
      ),
    );
  }
}
