import 'package:flutter/material.dart';

import '../../../../core/core_navigator.dart';
import '../../../../core/mini_program_loader/mini_program_registry.dart';
import '../../../../shared/design_system/constants/app_constants.dart';
import '../../../../shared/design_system/theme/color_scheme.dart';
import '../widgets/dashboard_section_header.dart';
import '../widgets/fulcrum_card.dart';
import '../widgets/mini_program_showcase_card.dart';

/// The Host Shell's main dashboard — the first screen an authenticated
/// user lands on (see `LoginPage`/`RegisterPage`, which both replace
/// the entire navigation stack with this route on success).
///
/// Laid out per the "Mizan Logic" home-screen design: a floating
/// glass [FulcrumCard] balancing the app's two foundational features
/// (Wallet and Chat), followed by two "Scales" of mini-programs —
/// B2C ("خدمات الأفراد والصحة") and B2B ("الأعمال والأصول") — each a
/// [MiniProgramShowcaseCard] linking into [CoreNavigator]'s existing
/// [CoreRoutes.miniProgram] route.
///
/// This page intentionally does *not* render every
/// [MiniProgramRegistry] entry generically (unlike the dynamic grid it
/// replaces): the "Mizan Logic" layout curates specific, named
/// mini-programs into specific sections, so it addresses each one by
/// [MiniProgram.id] instead of iterating [MiniProgramRegistry.programs].
/// [MiniProgramRegistry] is still the single source of truth for each
/// mini-program's icon, keeping that one detail from drifting between
/// the dashboard tile and the mini-program itself.
class HostDashboardPage extends StatelessWidget {
  HostDashboardPage({super.key, MiniProgramRegistry? registry})
      : _registry = registry ?? MiniProgramRegistry.instance;

  final MiniProgramRegistry _registry;

  // Placeholder content until the real Wallet/Chat features (both
  // still under construction in `core/wallet` and `core/chat`) are
  // wired up. Kept as clearly-named constants, rather than magic
  // literals inline, so replacing them later is a one-line change.
  static const String _placeholderWalletBalance = '2,450.00 ر.س';
  static const int _placeholderUnreadMessageCount = 3;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: MizanColors.background,
      body: Stack(
        children: <Widget>[
          const _HeaderBackdrop(),
          CustomScrollView(
            slivers: <Widget>[
              const SliverAppBar(
                backgroundColor: Colors.transparent,
                elevation: 0,
                automaticallyImplyLeading: false,
                expandedHeight: 96,
                flexibleSpace: FlexibleSpaceBar(
                  titlePadding: EdgeInsetsDirectional.only(
                    start: AppSpacing.lg,
                    bottom: AppSpacing.md,
                  ),
                  centerTitle: false,
                  title: Text(
                    'مرحباً بك في منصة الميزان',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ),
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(
                  AppSpacing.lg,
                  0,
                  AppSpacing.lg,
                  AppSpacing.xl,
                ),
                sliver: SliverList(
                  delegate: SliverChildListDelegate(<Widget>[
                    FulcrumCard(
                      walletBalance: _placeholderWalletBalance,
                      unreadMessageCount: _placeholderUnreadMessageCount,
                      onWalletTap: () =>
                          _showComingSoon(context, 'المحفظة الرقمية'),
                      onChatTap: () =>
                          _showComingSoon(context, 'الدردشة الآمنة'),
                    ),
                    const SizedBox(height: AppSpacing.xl),

                    // -- Scale 1 (B2C) --------------------------------
                    const DashboardSectionHeader(title: 'خدمات الأفراد والصحة'),
                    const SizedBox(height: AppSpacing.md),
                    MiniProgramShowcaseCard.wide(
                      title: 'Mizan Door',
                      subtitle: 'طابور العيادات',
                      icon: _registry.getById('mizan_door').icon,
                      onTap: () => _openMiniProgram(context, 'mizan_door'),
                    ),
                    const SizedBox(height: AppSpacing.xl),

                    // -- Scale 2 (B2B) --------------------------------
                    const DashboardSectionHeader(title: 'الأعمال والأصول'),
                    const SizedBox(height: AppSpacing.md),
                    // `IntrinsicHeight` bounds the row's height to its
                    // tallest child's natural size *before*
                    // `CrossAxisAlignment.stretch` tries to match both
                    // cards to it — without it, the row (sitting inside
                    // a height-unconstrained sliver list item) would
                    // hand its children an invalid infinite-height
                    // constraint while attempting to stretch them.
                    IntrinsicHeight(
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: <Widget>[
                          Expanded(
                            child: MiniProgramShowcaseCard.compact(
                              title: 'Tawazun Freight AI',
                              subtitle: 'الشحن والخدمات اللوجستية',
                              icon:
                                  _registry.getById('tawazun_freight_ai').icon,
                              onTap: () => _openMiniProgram(
                                  context, 'tawazun_freight_ai'),
                            ),
                          ),
                          const SizedBox(width: AppSpacing.md),
                          Expanded(
                            child: MiniProgramShowcaseCard.compact(
                              title: 'Oran Real Estate',
                              subtitle: 'العقارات والاستثمار',
                              icon: _registry.getById('oran_real_estate').icon,
                              onTap: () =>
                                  _openMiniProgram(context, 'oran_real_estate'),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ]),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  void _openMiniProgram(BuildContext context, String miniProgramId) {
    Navigator.of(context).pushNamed(
      CoreRoutes.miniProgram,
      arguments: miniProgramId,
    );
  }

  void _showComingSoon(BuildContext context, String featureName) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text('$featureName — قريباً.')));
  }
}

/// The navy-to-background gradient sitting behind the dashboard's
/// [SliverAppBar] and [FulcrumCard], giving the transparent app bar
/// something to show and the frosted-glass card something to blur.
class _HeaderBackdrop extends StatelessWidget {
  const _HeaderBackdrop();

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 280,
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: <Color>[
            MizanColors.navy,
            MizanColors.navy,
            MizanColors.background,
          ],
          stops: <double>[0.0, 0.55, 1.0],
        ),
      ),
    );
  }
}
