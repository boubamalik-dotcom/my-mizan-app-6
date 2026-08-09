import 'dart:ui';

import 'package:flutter/material.dart';

import '../../../../shared/design_system/constants/app_constants.dart';
import '../../../../shared/design_system/theme/color_scheme.dart';

/// The dashboard's "fulcrum" — the single card balancing the Super
/// App's two foundational Host Shell features, Wallet and Chat,
/// against each other (a "مِيزان"/scale is, after all, a balance).
///
/// Rendered as frosted glass (`BackdropFilter` + `ClipRRect`) so it
/// reads as floating above the navy header behind it, split evenly
/// between:
///
///  * **Right half** (first child — under the app's RTL ambient
///    [Directionality], a [Row]'s first child lands on the right):
///    "المحفظة الرقمية" (Digital Wallet), showing [walletBalanceContent].
///  * **Left half**: "الدردشة الآمنة" (Secure Chat), showing
///    [chatStatusContent] and, overlaid on its icon, [chatBadge].
///
/// Every live value on the card is injected as a [Widget] rather than
/// as data: this keeps [FulcrumCard] purely presentational and unaware
/// of `WalletCubit`, `ChatCubit`, or any other state-management choice.
class FulcrumCard extends StatelessWidget {
  const FulcrumCard({
    super.key,
    required this.walletBalanceContent,
    required this.chatStatusContent,
    this.chatBadge,
    this.onWalletTap,
    this.onChatTap,
  });

  /// The wallet half's balance figure — deliberately just this one
  /// small widget, not the whole card or even the whole wallet half.
  /// The caller (`HostDashboardPage`) wraps only this in a
  /// `BlocBuilder<WalletCubit, WalletState>` (via `WalletBalanceView`),
  /// so a Wallet state change (loading, loaded, error) repaints
  /// nothing else on the card — not the "الرصيد الحالي" caption above
  /// it, the wallet icon, the divider, or the Chat half beside it.
  /// [FulcrumCard] itself stays entirely unaware of `WalletCubit` or
  /// any other state-management choice — it only ever lays out
  /// whatever [Widget] it is handed.
  final Widget walletBalanceContent;

  /// The chat half's status line — the live counterpart to
  /// [walletBalanceContent], wrapped by the caller in its own
  /// `BlocBuilder` (see `ChatStatusText`).
  final Widget chatStatusContent;

  /// Small marker overlaid on the chat icon: an unread count, a
  /// connecting indicator, or an offline marker (see
  /// `ChatUnreadBadge`). Pass `null` — or a zero-sized widget — for no
  /// badge at all.
  final Widget? chatBadge;

  final VoidCallback? onWalletTap;
  final VoidCallback? onChatTap;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: AppRadius.cardRadius,
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18),
        child: Container(
          decoration: BoxDecoration(
            color: Colors.white.withOpacity(0.16),
            borderRadius: AppRadius.cardRadius,
            border: Border.all(color: Colors.white.withOpacity(0.3)),
            boxShadow: <BoxShadow>[
              BoxShadow(
                color: MizanColors.navyDark.withOpacity(0.3),
                blurRadius: 24,
                offset: const Offset(0, 10),
              ),
            ],
          ),
          child: SizedBox(
            // A concrete, generously-sized height rather than
            // `IntrinsicHeight`: `IntrinsicHeight` derives this from a
            // *separate, estimated* intrinsic-height layout pass over
            // each half's `Text` content, which can disagree by a
            // sub-pixel from that same content's *actual* layout
            // height once real (non-test) fonts are involved — a
            // well-known Flutter rounding gap that renders as a
            // spurious "RenderFlex overflowed" warning. A fixed height
            // sidesteps the mismatch entirely; `_FulcrumHalf`'s
            // `FittedBox` (below) is the second, independent
            // safeguard, gracefully shrinking content instead of
            // overflowing in the (now purely theoretical) case content
            // still doesn't fit, e.g. under extreme accessibility text
            // scaling.
            height: 180,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                Expanded(
                  child: _FulcrumHalf(
                    icon: Icons.account_balance_wallet_rounded,
                    label: 'المحفظة الرقمية',
                    onTap: onWalletTap,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: <Widget>[
                        const Text(
                          'الرصيد الحالي',
                          style: TextStyle(color: Colors.white70, fontSize: 12),
                        ),
                        const SizedBox(height: AppSpacing.xs),
                        walletBalanceContent,
                      ],
                    ),
                  ),
                ),
                Container(width: 1, color: Colors.white.withOpacity(0.25)),
                Expanded(
                  child: _FulcrumHalf(
                    icon: Icons.chat_bubble_rounded,
                    label: 'الدردشة الآمنة',
                    onTap: onChatTap,
                    badge: chatBadge,
                    child: chatStatusContent,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _FulcrumHalf extends StatelessWidget {
  const _FulcrumHalf({
    required this.icon,
    required this.label,
    required this.child,
    this.badge,
    this.onTap,
  });

  final IconData icon;
  final String label;
  final Widget child;
  final Widget? badge;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.sm,
            vertical: AppSpacing.md,
          ),
          // `FittedBox` is what actually makes the fixed height above
          // safe: it measures this `Column` at its natural size and
          // only ever scales it *down* (`BoxFit.scaleDown` never
          // enlarges) if it doesn't fit — imperceptibly, in the
          // ordinary case — instead of ever overflowing, regardless of
          // font-metric variance or a user's accessibility text-scale
          // setting.
          child: FittedBox(
            fit: BoxFit.scaleDown,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                _BadgedIcon(icon: icon, badge: badge),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  label,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w700,
                    fontSize: 15,
                  ),
                ),
                const SizedBox(height: AppSpacing.xs),
                child,
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _BadgedIcon extends StatelessWidget {
  const _BadgedIcon({required this.icon, this.badge});

  final IconData icon;
  final Widget? badge;

  @override
  Widget build(BuildContext context) {
    final Widget? badgeWidget = badge;

    return Stack(
      clipBehavior: Clip.none,
      children: <Widget>[
        CircleAvatar(
          radius: 22,
          backgroundColor: MizanColors.gold,
          child: Icon(icon, color: MizanColors.navy, size: 22),
        ),
        if (badgeWidget != null)
          PositionedDirectional(
            top: -4,
            // `PositionedDirectional.end` (rather than plain
            // `Positioned.right`) resolves against the ambient
            // [Directionality], so the badge stays pinned to the
            // icon's outer edge correctly under the app's RTL layout
            // instead of flipping to the wrong side.
            end: -4,
            child: badgeWidget,
          ),
      ],
    );
  }
}
