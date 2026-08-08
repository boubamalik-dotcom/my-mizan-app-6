import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../../../core/core_navigator.dart';
import '../../../../core/mini_program_loader/mini_program_registry.dart';
import '../../../../shared/design_system/constants/app_constants.dart';
import '../../../../shared/design_system/theme/color_scheme.dart';
import '../../../chat/presentation/state/chat_cubit.dart';
import '../../../chat/presentation/state/chat_state.dart';
import '../../../chat/presentation/widgets/chat_status_text.dart';
import '../../../chat/presentation/widgets/chat_unread_badge.dart';
import '../../../wallet/presentation/state/wallet_cubit.dart';
import '../../../wallet/presentation/state/wallet_state.dart';
import '../../../wallet/presentation/widgets/wallet_balance_view.dart';
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
  HostDashboardPage({
    super.key,
    MiniProgramRegistry? registry,
    WalletCubit? walletCubit,
    ChatCubit? chatCubit,
  })  : _registry = registry ?? MiniProgramRegistry.instance,
        _walletCubitOverride = walletCubit,
        _chatCubitOverride = chatCubit;

  final MiniProgramRegistry _registry;

  /// Injectable for tests, which need full control over the wallet's
  /// data source (e.g. a [WalletCubit] backed by a mocked
  /// `WalletRepository` instead of a real network call). Either this
  /// or a fresh production [WalletCubit] is immediately told to
  /// [WalletCubit.loadWalletData] in [build] — which is what satisfies
  /// "load the wallet on entering the dashboard" without this page
  /// needing to become a `StatefulWidget` just to call something from
  /// `initState`.
  final WalletCubit? _walletCubitOverride;

  /// The Chat counterpart of [_walletCubitOverride]: injectable for
  /// tests (which must never open a real WebSocket), and otherwise a
  /// fresh [ChatCubit] told to [ChatCubit.initializeChat] in [build],
  /// right alongside the wallet's load.
  final ChatCubit? _chatCubitOverride;

  @override
  Widget build(BuildContext context) {
    return MultiBlocProvider(
      // Both features kick off their own load the moment the dashboard
      // is built — whether these are fresh production cubits or
      // test-injected overrides — so "load on entering the dashboard"
      // holds regardless of which instances are in play, and
      // callers/tests never need to remember to trigger them.
      // `BlocProvider` also closes both when this page is disposed,
      // which is what tears the chat WebSocket down on logout (see
      // `ChatCubit.close`).
      providers: [
        BlocProvider<WalletCubit>(
          create: (_) =>
              (_walletCubitOverride ?? WalletCubit())..loadWalletData(),
        ),
        BlocProvider<ChatCubit>(
          create: (_) => (_chatCubitOverride ?? ChatCubit())..initializeChat(),
        ),
      ],
      // `Builder` so everything below — including the tap callbacks
      // that `context.read<WalletCubit>()` — gets a context *beneath*
      // the providers. Using this method's own `context` there would
      // look up from above them and throw `ProviderNotFoundException`.
      child: Builder(
        builder: (BuildContext context) => Scaffold(
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
                          walletBalanceContent:
                              BlocBuilder<WalletCubit, WalletState>(
                            builder:
                                (BuildContext context, WalletState state) =>
                                    WalletBalanceView(state: state),
                          ),
                          chatBadge: BlocBuilder<ChatCubit, ChatState>(
                            builder: (BuildContext context, ChatState state) =>
                                ChatUnreadBadge(state: state),
                          ),
                          chatStatusContent: BlocBuilder<ChatCubit, ChatState>(
                            builder: (BuildContext context, ChatState state) =>
                                ChatStatusText(state: state),
                          ),
                          onWalletTap: () => _openWalletDetails(context),
                          onChatTap: () =>
                              _showComingSoon(context, 'الدردشة الآمنة'),
                        ),
                        const SizedBox(height: AppSpacing.xl),

                        // -- Scale 1 (B2C) ------------------------------
                        const DashboardSectionHeader(
                          title: 'خدمات الأفراد والصحة',
                        ),
                        const SizedBox(height: AppSpacing.md),
                        MiniProgramShowcaseCard.wide(
                          title: 'Mizan Door',
                          subtitle: 'طابور العيادات',
                          icon: _registry.getById('mizan_door').icon,
                          onTap: () => _openMiniProgram(context, 'mizan_door'),
                        ),
                        const SizedBox(height: AppSpacing.xl),

                        // -- Scale 2 (B2B) ------------------------------
                        const DashboardSectionHeader(title: 'الأعمال والأصول'),
                        const SizedBox(height: AppSpacing.md),
                        // `IntrinsicHeight` bounds the row's height to
                        // its tallest child's natural size *before*
                        // `CrossAxisAlignment.stretch` tries to match
                        // both cards to it — without it, the row
                        // (sitting inside a height-unconstrained sliver
                        // list item) would hand its children an invalid
                        // infinite-height constraint while attempting to
                        // stretch them.
                        IntrinsicHeight(
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: <Widget>[
                              Expanded(
                                child: MiniProgramShowcaseCard.compact(
                                  title: 'Tawazun Freight AI',
                                  subtitle: 'الشحن والخدمات اللوجستية',
                                  icon: _registry
                                      .getById('tawazun_freight_ai')
                                      .icon,
                                  onTap: () => _openMiniProgram(
                                    context,
                                    'tawazun_freight_ai',
                                  ),
                                ),
                              ),
                              const SizedBox(width: AppSpacing.md),
                              Expanded(
                                child: MiniProgramShowcaseCard.compact(
                                  title: 'Oran Real Estate',
                                  subtitle: 'العقارات والاستثمار',
                                  icon: _registry
                                      .getById('oran_real_estate')
                                      .icon,
                                  onTap: () => _openMiniProgram(
                                    context,
                                    'oran_real_estate',
                                  ),
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
        ),
      ),
    );
  }

  /// Opens the full Wallet screen and, if a deposit/withdrawal/transfer
  /// happened while it was open, re-reads the balance into *this*
  /// page's cubit — `WalletDetailsPage` runs its own cubit, so the
  /// dashboard would otherwise come back showing a stale figure.
  Future<void> _openWalletDetails(BuildContext context) async {
    final WalletCubit cubit = context.read<WalletCubit>();
    final bool? balanceChanged = await Navigator.of(context).pushNamed<bool>(
      CoreRoutes.walletDetails,
    );
    // `null` means the page was popped by the system back gesture,
    // which cannot carry a result — refresh rather than risk leaving a
    // stale balance on screen. An explicit `false` (the app-bar arrow
    // after no transactions) is the only case that skips the request.
    if (balanceChanged ?? true) {
      await cubit.loadWalletData();
    }
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
