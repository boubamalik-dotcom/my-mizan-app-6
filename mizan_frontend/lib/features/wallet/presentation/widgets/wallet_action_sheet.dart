import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../../shared/design_system/constants/app_constants.dart';
import '../../../../shared/design_system/theme/color_scheme.dart';
import '../../../../shared/design_system/widgets/custom_button.dart';
import '../../../../shared/design_system/widgets/custom_text_field.dart';
import '../../../../shared/exceptions/app_exception.dart';
import '../../../../shared/utils/validators.dart';

/// What the sheet collected, handed back to the caller on confirm.
class WalletActionInput {
  const WalletActionInput({required this.amount, this.destinationWalletId});

  final double amount;

  /// Only populated for a transfer.
  final String? destinationWalletId;
}

/// Runs the submitted action, throwing an [AppException] (whose
/// `message` is display-ready Arabic) if it fails.
typedef WalletActionSubmit = Future<void> Function(WalletActionInput input);

/// The modal sheet behind every wallet action — deposit, withdrawal,
/// and transfer all share one implementation, differing only in their
/// title, icon, confirm-button label, and whether a destination field
/// is shown.
///
/// Keeps its own `_isSubmitting` flag rather than reading it from
/// `WalletCubit`: the spinner belongs to *this* form, and driving it
/// locally means the sheet stays open (with the user's input intact)
/// when a transaction is rejected, instead of being torn down by a
/// state change.
class WalletActionSheet extends StatefulWidget {
  const WalletActionSheet({
    super.key,
    required this.title,
    required this.icon,
    required this.confirmLabel,
    required this.onSubmit,
    this.requiresDestination = false,
    this.currency,
  });

  final String title;
  final IconData icon;
  final String confirmLabel;
  final WalletActionSubmit onSubmit;

  /// Whether to collect a destination wallet id (transfers only).
  final bool requiresDestination;

  /// Shown as the amount field's suffix, e.g. `DZD`.
  final String? currency;

  /// Presents this sheet, returning `true` only if the action
  /// completed successfully.
  static Future<bool> show(
    BuildContext context, {
    required String title,
    required IconData icon,
    required String confirmLabel,
    required WalletActionSubmit onSubmit,
    bool requiresDestination = false,
    String? currency,
  }) async {
    final bool? succeeded = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (BuildContext sheetContext) => WalletActionSheet(
        title: title,
        icon: icon,
        confirmLabel: confirmLabel,
        onSubmit: onSubmit,
        requiresDestination: requiresDestination,
        currency: currency,
      ),
    );
    return succeeded ?? false;
  }

  @override
  State<WalletActionSheet> createState() => _WalletActionSheetState();
}

class _WalletActionSheetState extends State<WalletActionSheet> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  final TextEditingController _amountController = TextEditingController();
  final TextEditingController _destinationController = TextEditingController();

  bool _isSubmitting = false;

  @override
  void dispose() {
    _amountController.dispose();
    _destinationController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final FormState? form = _formKey.currentState;
    if (form == null || !form.validate()) return;

    final double? amount = Validators.parseAmount(_amountController.text);
    if (amount == null) return;

    setState(() => _isSubmitting = true);
    try {
      await widget.onSubmit(
        WalletActionInput(
          amount: amount,
          destinationWalletId: widget.requiresDestination
              ? _destinationController.text.trim()
              : null,
        ),
      );
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } on AppException catch (error) {
      if (!mounted) return;
      setState(() => _isSubmitting = false);
      _showError(error.message);
    } catch (_) {
      if (!mounted) return;
      setState(() => _isSubmitting = false);
      _showError('تعذّر إتمام العملية. يرجى المحاولة مرة أخرى.');
    }
  }

  void _showError(String message) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(message),
          backgroundColor: MizanColors.error,
        ),
      );
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      // Lifts the sheet above the on-screen keyboard so the confirm
      // button is never hidden behind it.
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      child: Container(
        decoration: const BoxDecoration(
          color: MizanColors.surface,
          borderRadius: BorderRadius.vertical(
            top: Radius.circular(AppRadius.card),
          ),
        ),
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.lg,
          AppSpacing.md,
          AppSpacing.lg,
          AppSpacing.lg,
        ),
        child: SafeArea(
          top: false,
          child: Form(
            key: _formKey,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                const _SheetGrabHandle(),
                const SizedBox(height: AppSpacing.md),
                _SheetHeader(icon: widget.icon, title: widget.title),
                const SizedBox(height: AppSpacing.lg),
                if (widget.requiresDestination) ...<Widget>[
                  MizanTextField(
                    controller: _destinationController,
                    label: 'معرّف محفظة المستلم',
                    hint: 'b6e6b4b0-…',
                    prefixIcon: Icons.account_balance_wallet_outlined,
                    textDirection: TextDirection.ltr,
                    textInputAction: TextInputAction.next,
                    enabled: !_isSubmitting,
                    validator: Validators.walletId,
                  ),
                  const SizedBox(height: AppSpacing.md),
                ],
                MizanTextField(
                  controller: _amountController,
                  label:
                      'المبلغ${widget.currency != null ? ' (${widget.currency})' : ''}',
                  hint: '0.00',
                  keyboardType: const TextInputType.numberWithOptions(
                    decimal: true,
                  ),
                  inputFormatters: <TextInputFormatter>[
                    FilteringTextInputFormatter.allow(RegExp(r'[0-9.,٫]')),
                  ],
                  prefixIcon: Icons.payments_outlined,
                  textDirection: TextDirection.ltr,
                  textInputAction: TextInputAction.done,
                  enabled: !_isSubmitting,
                  validator: Validators.amount,
                ),
                const SizedBox(height: AppSpacing.lg),
                PrimaryButton(
                  label: widget.confirmLabel,
                  isLoading: _isSubmitting,
                  onPressed: _submit,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _SheetGrabHandle extends StatelessWidget {
  const _SheetGrabHandle();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        height: 4,
        width: 44,
        decoration: BoxDecoration(
          color: MizanColors.textSecondary.withOpacity(0.35),
          borderRadius: BorderRadius.circular(2),
        ),
      ),
    );
  }
}

class _SheetHeader extends StatelessWidget {
  const _SheetHeader({required this.icon, required this.title});

  final IconData icon;
  final String title;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        CircleAvatar(
          radius: 20,
          backgroundColor: MizanColors.gold.withOpacity(0.15),
          child: Icon(icon, color: MizanColors.gold, size: 20),
        ),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: Text(
            title,
            style: Theme.of(context).textTheme.titleLarge,
          ),
        ),
      ],
    );
  }
}
