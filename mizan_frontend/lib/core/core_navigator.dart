import 'package:flutter/material.dart';

import '../features/auth/presentation/pages/login_page.dart';
import '../features/auth/presentation/pages/register_page.dart';
import '../features/chat/presentation/pages/chat_room_page.dart';
import '../features/dashboard/presentation/pages/dashboard_page.dart';
import '../mini_programs/mizan_door/presentation/pages/queue_dashboard_page.dart';
import '../mini_programs/oran_real_estate/presentation/pages/property_listing_page.dart';
import '../features/wallet/presentation/pages/wallet_details_page.dart';
import '../shared/network/interceptors.dart' show kLoginRouteName;
import 'mini_program_loader/mini_program_base.dart';
import 'mini_program_loader/mini_program_loader.dart';

/// Route names recognized by the host shell's [CoreNavigator].
///
/// Kept as a dedicated, non-instantiable class rather than loose
/// top-level constants so route names are always accessed with a
/// clear, greppable `CoreRoutes.` prefix.
final class CoreRoutes {
  const CoreRoutes._();

  /// The host dashboard listing every available mini-program.
  static const String dashboard = '/';

  /// A dynamically-loaded mini-program. Requires the mini-program's
  /// [MiniProgram.id] as the route's `arguments`.
  static const String miniProgram = '/mini-program';

  /// "تسجيل الدخول" — the Host Shell's unauthenticated entry point.
  ///
  /// Reuses `shared/network/interceptors.dart`'s [kLoginRouteName]
  /// rather than redeclaring the string, since `AuthInterceptor`
  /// (which lives in `shared/` and must never depend on `core/`)
  /// also needs to name this exact route to force a logout redirect
  /// on a `401`. This keeps the two in permanent agreement.
  static const String login = kLoginRouteName;

  /// "إنشاء حساب" — new-account registration.
  static const String register = '/auth/register';

  /// "المحفظة الرقمية" — the full Wallet screen (balance plus deposit,
  /// withdraw, and transfer actions). Pops `true` when the balance
  /// changed while it was open, so the dashboard can refresh.
  static const String walletDetails = '/wallet';

  /// "الدردشة الآمنة" — the chat room: history plus live messaging.
  static const String chatRoom = '/chat';

  /// "طابور العيادات" — the Mizan Door mini-program's queue screen.
  ///
  /// A direct route in addition to reaching the same page through
  /// [miniProgram], for the same reason as [realEstate]: the dashboard
  /// card pushes this so the destination is addressable by name, while
  /// the mini-program loader keeps working for anything going through
  /// the registry. Both render `QueueDashboardPage`.
  static const String mizanDoor = '/mizan-door';

  /// "عقارات وهران" — the Oran Real Estate mini-program's listing
  /// screen.
  ///
  /// A direct route *in addition to* reaching the same page through
  /// [miniProgram]: the dashboard card pushes this so the destination
  /// is addressable by name, while the mini-program loader keeps
  /// working for anything that goes through the registry. Both render
  /// `PropertyListingPage`.
  static const String realEstate = '/real-estate';
}

/// Host Shell routing table.
///
/// [CoreNavigator] is the single place responsible for turning named
/// routes into pages. It knows about [HostDashboardPage] and the
/// generic [MiniProgramHostPage], but never about any specific
/// mini-program implementation — new mini-programs are wired in
/// purely through [MiniProgramRegistry], so this file never needs to
/// change when the catalog of mini-programs grows (Open/Closed
/// Principle).
final class CoreNavigator {
  const CoreNavigator._();

  /// Wire this into `MaterialApp.onGenerateRoute` to activate the host
  /// shell's routing:
  ///
  /// ```dart
  /// MaterialApp(
  ///   initialRoute: CoreRoutes.dashboard,
  ///   onGenerateRoute: CoreNavigator.onGenerateRoute,
  /// )
  /// ```
  /// Builds the startup navigation stack as exactly **one** route.
  ///
  /// Flutter's default behaviour splits a multi-segment `initialRoute`
  /// into a whole stack — `'/auth/login'` generates `'/'`, `'/auth'`,
  /// *then* `'/auth/login'`. Since `'/'` is [CoreRoutes.dashboard], the
  /// default would silently build a `HostDashboardPage` underneath the
  /// login screen before anyone has signed in: it would fire
  /// authenticated wallet and chat calls with no token, and its
  /// `ChatCubit` would open a socket that the post-login dashboard's
  /// `ChatCubit` then fought with over the shared `ChatRepository`,
  /// leaving the badge stuck on "غير متصل حاليًا" while the socket was
  /// in fact healthy.
  ///
  /// Returning a single route keeps the auth gate meaning what it says:
  /// nothing behind the login screen exists until the user is past it.
  static List<Route<dynamic>> onGenerateInitialRoutes(String initialRoute) {
    return <Route<dynamic>>[
      onGenerateRoute(RouteSettings(name: initialRoute)),
    ];
  }

  static Route<dynamic> onGenerateRoute(RouteSettings settings) {
    switch (settings.name) {
      case CoreRoutes.login:
        return MaterialPageRoute<void>(
          settings: settings,
          builder: (_) => const LoginPage(),
        );

      case CoreRoutes.register:
        return MaterialPageRoute<void>(
          settings: settings,
          builder: (_) => const RegisterPage(),
        );

      case CoreRoutes.dashboard:
        return MaterialPageRoute<void>(
          settings: settings,
          builder: (_) => HostDashboardPage(),
        );

      // Typed `bool` (unlike the `void` routes around it): the page
      // reports back whether the balance changed while it was open.
      case CoreRoutes.walletDetails:
        return MaterialPageRoute<bool>(
          settings: settings,
          builder: (_) => const WalletDetailsPage(),
        );

      case CoreRoutes.chatRoom:
        return MaterialPageRoute<void>(
          settings: settings,
          builder: (_) => const ChatRoomPage(),
        );

      case CoreRoutes.realEstate:
        return MaterialPageRoute<void>(
          settings: settings,
          builder: (_) => const PropertyListingPage(),
        );

      case CoreRoutes.mizanDoor:
        return MaterialPageRoute<void>(
          settings: settings,
          builder: (_) => const QueueDashboardPage(),
        );

      case CoreRoutes.miniProgram:
        final Object? miniProgramId = settings.arguments;
        if (miniProgramId is! String || miniProgramId.isEmpty) {
          return _errorRoute(
            settings,
            'Route "${CoreRoutes.miniProgram}" requires a non-empty '
            'mini-program id as its arguments.',
          );
        }
        return MaterialPageRoute<void>(
          settings: settings,
          builder: (_) => MiniProgramHostPage(miniProgramId: miniProgramId),
        );

      default:
        return _errorRoute(
          settings,
          'No route defined for "${settings.name}".',
        );
    }
  }

  static Route<dynamic> _errorRoute(RouteSettings settings, String message) {
    return MaterialPageRoute<void>(
      settings: settings,
      builder: (_) => _RouteErrorPage(message: message),
    );
  }
}

/// Generic host page for any mini-program.
///
/// Lazily loads the requested mini-program through [MiniProgramLoader]
/// (showing a loading indicator while [MiniProgram.initialize] runs)
/// and then delegates rendering entirely to
/// [MiniProgram.buildRootWidget]. This class never contains
/// mini-program-specific logic, which is what keeps the host shell
/// open for extension without modification.
class MiniProgramHostPage extends StatefulWidget {
  const MiniProgramHostPage({
    super.key,
    required this.miniProgramId,
    MiniProgramLoader? loader,
  }) : _loaderOverride = loader;

  /// The [MiniProgram.id] to load and display.
  final String miniProgramId;

  final MiniProgramLoader? _loaderOverride;

  @override
  State<MiniProgramHostPage> createState() => _MiniProgramHostPageState();
}

class _MiniProgramHostPageState extends State<MiniProgramHostPage> {
  late final MiniProgramLoader _loader =
      widget._loaderOverride ?? MiniProgramLoader.instance;
  late final Future<MiniProgram> _future = _loader.load(widget.miniProgramId);

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<MiniProgram>(
      future: _future,
      builder: (BuildContext context, AsyncSnapshot<MiniProgram> snapshot) {
        if (snapshot.hasError) {
          return _RouteErrorPage(
            message:
                'Failed to load "${widget.miniProgramId}": ${snapshot.error}',
          );
        }
        if (!snapshot.hasData) {
          return const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          );
        }
        return snapshot.data!.buildRootWidget(context);
      },
    );
  }
}

/// Minimal fallback page shown when routing fails (unknown route or a
/// mini-program that could not be loaded), instead of crashing the
/// host shell.
class _RouteErrorPage extends StatelessWidget {
  const _RouteErrorPage({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Something went wrong')),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(message, textAlign: TextAlign.center),
        ),
      ),
    );
  }
}
