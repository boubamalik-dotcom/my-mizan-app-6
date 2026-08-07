import 'package:flutter/material.dart';

/// Contract that every dynamically-loadable mini-program in the Mizan
/// Super App host shell must satisfy.
///
/// A [MiniProgram] is a self-contained Clean Architecture module living
/// under `lib/mini_programs/<name>/`. It never depends on other
/// mini-programs and only depends on the shared cross-cutting layer
/// (`lib/shared/`). This keeps every mini-program pluggable: it can be
/// registered, lazily loaded, and unloaded by the host shell without
/// affecting the rest of the app (Open/Closed Principle — the host
/// shell is open to new mini-programs but never needs to be modified
/// to support them).
///
/// To add a new mini-program:
///  1. Implement this interface (or extend [BaseMiniProgram] for sane
///     defaults so only identity, theming, and UI need to be written).
///  2. Register an instance of it in `MiniProgramRegistry`.
///
/// No other host-shell code needs to change — the dashboard, router,
/// and loader all discover mini-programs entirely through the
/// registry (Dependency Inversion Principle: high-level host-shell
/// modules depend on this abstraction, never on concrete
/// mini-programs).
abstract class MiniProgram {
  /// Stable, unique identifier for this mini-program (for example
  /// `"tawazun_freight_ai"`). Used as the registry key and as the
  /// route argument when navigating to the mini-program.
  String get id;

  /// Human-readable name shown on the host dashboard tile and in the
  /// mini-program's own app bar.
  String get title;

  /// Short, user-facing description of what the mini-program does.
  /// Displayed on the dashboard tile beneath the [title].
  String get description;

  /// Icon representing the mini-program on the host dashboard.
  IconData get icon;

  /// Accent color used to theme the mini-program's dashboard tile and
  /// app bar, keeping each mini-program visually distinct.
  Color get accentColor;

  /// Whether [initialize] has completed and the mini-program is ready
  /// to build its UI. The mini-program loader uses this to avoid
  /// re-initializing an already-loaded mini-program.
  bool get isInitialized;

  /// Performs any asynchronous setup the mini-program needs before its
  /// UI can be built (for example warming a local cache, fetching a
  /// feature flag, or wiring up its internal dependency-injection
  /// scope).
  ///
  /// Called exactly once by the mini-program loader, the first time
  /// the mini-program is opened. Implementations should be idempotent
  /// and fast — this directly gates how "lightweight" lazy loading
  /// feels to the user.
  Future<void> initialize();

  /// Builds the mini-program's root widget (typically wrapping its own
  /// `Scaffold`, BLoC providers, and internal navigation).
  ///
  /// Must only be called after [initialize] has completed.
  Widget buildRootWidget(BuildContext context);

  /// Builds the [Route] used to push this mini-program onto the host
  /// shell's [Navigator] when opened from the dashboard.
  Route<void> getRoute();

  /// Releases any resources acquired in [initialize] (streams,
  /// controllers, sockets, etc.) when the mini-program loader evicts
  /// this mini-program from memory.
  Future<void> dispose();
}

/// Convenience base class implementing the boilerplate parts of
/// [MiniProgram] so concrete mini-programs only need to override what
/// makes them unique: identity, theming, and [buildRootWidget].
///
/// Every subclass remains a fully valid [MiniProgram] (Liskov
/// Substitution Principle) — the host shell never needs to know
/// whether it is working with a [BaseMiniProgram] or a from-scratch
/// [MiniProgram] implementation.
abstract class BaseMiniProgram implements MiniProgram {
  bool _isInitialized = false;

  @override
  bool get isInitialized => _isInitialized;

  /// Default initialization is a no-op that simply flips
  /// [isInitialized]. Override to perform real async setup, calling
  /// `await super.initialize()` last so [isInitialized] still reflects
  /// completion.
  @override
  @mustCallSuper
  Future<void> initialize() async {
    _isInitialized = true;
  }

  /// Default route wraps [buildRootWidget] in a [MaterialPageRoute].
  /// Override for custom transitions (e.g. a full-screen dialog).
  @override
  Route<void> getRoute() {
    return MaterialPageRoute<void>(
      settings: RouteSettings(name: '/mini-program/$id'),
      builder: buildRootWidget,
    );
  }

  /// Default disposal simply resets [isInitialized] so the
  /// mini-program can be safely reloaded later. Override to close
  /// streams, sockets, or controllers, calling `await super.dispose()`
  /// last.
  @override
  @mustCallSuper
  Future<void> dispose() async {
    _isInitialized = false;
  }
}
