import 'package:flutter/foundation.dart';

import 'mini_program_base.dart';
import 'mini_program_registry.dart';

/// Manages the lazy-loading lifecycle of mini-programs so the host
/// shell keeps its memory footprint small even as the number of
/// installed mini-programs grows.
///
/// Mini-programs are *not* initialized when the app starts. Each is
/// only initialized (via [MiniProgram.initialize]) the first time a
/// user opens it from the host dashboard, and is evicted (via
/// [MiniProgram.dispose]) once more than [maxCachedPrograms] are held
/// in memory at once, or when explicitly [unload]ed.
///
/// [MiniProgramLoader] depends only on the [MiniProgram] abstraction
/// and an injectable [MiniProgramRegistry], so it can be unit-tested
/// with fake mini-programs and never needs to know about concrete
/// mini-programs such as Tawazun Freight AI or Mizan Door (Dependency
/// Inversion Principle). It extends [ChangeNotifier] so hosting
/// widgets can reactively show a loading indicator while a
/// mini-program initializes.
class MiniProgramLoader extends ChangeNotifier {
  MiniProgramLoader({
    MiniProgramRegistry? registry,
    this.maxCachedPrograms = 2,
  })  : assert(maxCachedPrograms > 0, 'maxCachedPrograms must be positive'),
        _registry = registry ?? MiniProgramRegistry.instance;

  /// Default, app-wide loader instance. Widgets that don't need a
  /// custom cache size or a fake registry for testing can use this
  /// directly instead of threading a loader through the widget tree.
  static final MiniProgramLoader instance = MiniProgramLoader();

  final MiniProgramRegistry _registry;

  /// Maximum number of mini-programs kept initialized/cached at once.
  /// When exceeded, the least-recently-used mini-program is disposed.
  /// Keeping this small is what makes the host shell "lightweight".
  final int maxCachedPrograms;

  final Map<String, MiniProgram> _loaded = <String, MiniProgram>{};
  final List<String> _recencyOrder = <String>[];
  String? _loadingId;

  /// The id of the mini-program currently being initialized, or
  /// `null` if no load is in progress. Hosts can watch this (via
  /// [ChangeNotifier]) to show a loading indicator.
  String? get loadingId => _loadingId;

  /// Whether any mini-program is currently being initialized.
  bool get isLoading => _loadingId != null;

  /// Mini-programs currently kept in memory, least-recently-used
  /// first.
  List<MiniProgram> get loadedPrograms => List.unmodifiable(
        _recencyOrder.map((String id) => _loaded[id]!),
      );

  /// Returns whether the mini-program with [id] is already loaded and
  /// initialized, without triggering a load.
  bool isLoaded(String id) => _loaded.containsKey(id);

  /// Resolves the mini-program registered under [id], initializing it
  /// on first access and evicting the least-recently-used mini-program
  /// if [maxCachedPrograms] is exceeded.
  ///
  /// Safe to call repeatedly — subsequent calls for an already-loaded
  /// mini-program return the cached instance immediately without
  /// re-running [MiniProgram.initialize].
  ///
  /// Throws a [StateError] (propagated from [MiniProgramRegistry]) if
  /// no mini-program is registered under [id].
  Future<MiniProgram> load(String id) async {
    final MiniProgram? cached = _loaded[id];
    if (cached != null) {
      _markRecentlyUsed(id);
      return cached;
    }

    final MiniProgram program = _registry.getById(id);

    _loadingId = id;
    notifyListeners();
    try {
      await program.initialize();
    } finally {
      _loadingId = null;
    }

    _loaded[id] = program;
    _markRecentlyUsed(id);
    await _evictLeastRecentlyUsedIfNeeded();
    notifyListeners();
    return program;
  }

  void _markRecentlyUsed(String id) {
    _recencyOrder
      ..remove(id)
      ..add(id);
  }

  Future<void> _evictLeastRecentlyUsedIfNeeded() async {
    while (_recencyOrder.length > maxCachedPrograms) {
      final String leastRecentId = _recencyOrder.removeAt(0);
      final MiniProgram? evicted = _loaded.remove(leastRecentId);
      await evicted?.dispose();
    }
  }

  /// Explicitly unloads the mini-program with [id], disposing its
  /// resources immediately rather than waiting for LRU eviction.
  Future<void> unload(String id) async {
    final MiniProgram? program = _loaded.remove(id);
    _recencyOrder.remove(id);
    if (program != null) {
      await program.dispose();
      notifyListeners();
    }
  }

  /// Unloads every currently-loaded mini-program. Useful when the host
  /// shell wants to aggressively free memory (for example on a
  /// low-memory warning).
  Future<void> unloadAll() async {
    final List<String> ids = List<String>.from(_recencyOrder);
    for (final String id in ids) {
      await unload(id);
    }
  }
}
