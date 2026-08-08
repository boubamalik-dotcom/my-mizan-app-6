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
///    "المحفظة الرقمية" (Digital Wallet), showing [walletBalance].
///  * **Left half**: "الدردشة الآمنة" (Secure Chat), showing an
///    unread-message badge when [unreadMessageCount] is positive.
class FulcrumCard extends StatelessWidget {
  const FulcrumCard({
    super.key,
    required this.walletBalance,
    this.unreadMessageCount = 0,
    this.onWalletTap,
    this.onChatTap,
  });

  /// Pre-formatted balance text (e.g. `"2,450.00 ر.س"`). Formatting is
  /// the caller's responsibility — this widget only lays it out — so
  /// it stays decoupled from wherever the real Wallet balance
  /// eventually comes from.
  final String walletBalance;

  /// Number of unread chat messages; the badge is hidden entirely
  /// when this is `0`.
  final int unreadMessageCount;

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
          child: IntrinsicHeight(
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
                        Text(
                          walletBalance,
                          textDirection: TextDirection.ltr,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 18,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
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
                    badgeCount: unreadMessageCount,
                    child: const Text(
                      'محادثات مشفّرة بالكامل',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.white70, fontSize: 12),
                    ),
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
    this.badgeCount = 0,
    this.onTap,
  });

  final IconData icon;
  final String label;
  final Widget child;
  final int badgeCount;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          // A few extra pixels of bottom padding beyond the symmetric
          // `AppSpacing.md` used everywhere else: `IntrinsicHeight`
          // (in `FulcrumCard.build`) sizes this row from an *estimated*
          // intrinsic height of each half's `Text` content, which can
          // land a hair short of that same content's *actual* layout
          // height once real fonts are involved — a well-known,
          // effectively-invisible sub-pixel rounding gap between
          // Flutter's intrinsic-height and normal layout passes. This
          // margin absorbs that gap so it never renders as an overflow
          // warning.
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.sm,
            AppSpacing.md,
            AppSpacing.sm,
            AppSpacing.md + 6,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              _BadgedIcon(icon: icon, badgeCount: badgeCount),
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
    );
  }
}

class _BadgedIcon extends StatelessWidget {
  const _BadgedIcon({required this.icon, required this.badgeCount});

  final IconData icon;
  final int badgeCount;

  @override
  Widget build(BuildContext context) {
    return Stack(
      clipBehavior: Clip.none,
      children: <Widget>[
        CircleAvatar(
          radius: 22,
          backgroundColor: MizanColors.gold,
          child: Icon(icon, color: MizanColors.navy, size: 22),
        ),
        if (badgeCount > 0)
          PositionedDirectional(
            top: -4,
            // `PositionedDirectional.end` (rather than plain
            // `Positioned.right`) resolves against the ambient
            // [Directionality], so the badge stays pinned to the
            // icon's outer edge correctly under the app's RTL layout
            // instead of flipping to the wrong side.
            end: -4,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
              constraints: const BoxConstraints(minWidth: 18),
              decoration: BoxDecoration(
                color: MizanColors.error,
                borderRadius: BorderRadius.circular(9),
                border: Border.all(color: Colors.white, width: 1.5),
              ),
              child: Text(
                badgeCount > 9 ? '9+' : '$badgeCount',
                textAlign: TextAlign.center,
                textDirection: TextDirection.ltr,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 10,
                  fontWeight: FontWeight.w700,
                  height: 1.3,
                ),
              ),
            ),
          ),
      ],
    );
  }
}
