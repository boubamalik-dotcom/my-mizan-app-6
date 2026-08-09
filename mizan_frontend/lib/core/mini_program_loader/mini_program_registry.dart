import 'package:flutter/foundation.dart' show visibleForTesting;

import '../../mini_programs/mizan_door/mizan_door_mini_program.dart';
import '../../mini_programs/oran_real_estate/oran_real_estate_mini_program.dart';
import '../../mini_programs/tawazun_freight_ai/tawazun_freight_ai_mini_program.dart';
import 'mini_program_base.dart';

/// Central catalog of every mini-program available in the Mizan Super
/// App host shell.
///
/// Implemented as a Singleton so the host dashboard, deep links, and
/// the mini-program loader all resolve mini-programs from the exact
/// same source of truth. The registry itself never builds UI or
/// manages mini-program lifecycles — that is the loader's job (Single
/// Responsibility Principle).
///
/// This is the app's *composition root* for mini-programs: it is the
/// one place allowed to import concrete mini-program entry points.
/// Adding a new mini-program only requires appending one line to
/// [_bootstrap]; nothing else in the host shell (dashboard, router,
/// loader) needs to change.
class MiniProgramRegistry {
  MiniProgramRegistry._internal() {
    _bootstrap();
  }

  /// The single, shared instance of the registry used throughout the
  /// app. Widgets/services that need a custom set of mini-programs
  /// (for example in tests) can still construct their own registry
  /// via [MiniProgramRegistry.forTesting].
  static final MiniProgramRegistry instance = MiniProgramRegistry._internal();

  /// Creates an empty registry for unit/widget tests, bypassing
  /// [_bootstrap] so tests can register fake [MiniProgram]s instead of
  /// the real ones.
  @visibleForTesting
  MiniProgramRegistry.forTesting();

  final Map<String, MiniProgram> _programs = <String, MiniProgram>{};

  /// Registers the mini-programs shipped with the app. Keep this list
  /// declarative: it is the only place that needs to change when a
  /// mini-program is added, removed, or temporarily disabled.
  void _bootstrap() {
    registerAll(<MiniProgram>[
      TawazunFreightAiMiniProgram(),
      MizanDoorMiniProgram(),
      OranRealEstateMiniProgram(),
    ]);
  }

  /// All registered mini-programs, in registration order. The
  /// returned list is unmodifiable so the registry stays the single
  /// source of truth for mutations.
  List<MiniProgram> get programs => List.unmodifiable(_programs.values);

  /// Registers a single [program]. If a mini-program with the same
  /// [MiniProgram.id] already exists it is replaced, which is useful
  /// for tests that need to stub out a mini-program.
  void register(MiniProgram program) {
    _programs[program.id] = program;
  }

  /// Registers several mini-programs at once, preserving order.
  void registerAll(Iterable<MiniProgram> programs) {
    for (final MiniProgram program in programs) {
      register(program);
    }
  }

  /// Removes the mini-program with the given [id], if present.
  void unregister(String id) {
    _programs.remove(id);
  }

  /// Looks up a mini-program by [id], returning `null` if none is
  /// registered under that id.
  MiniProgram? find(String id) => _programs[id];

  /// Looks up a mini-program by [id], throwing a [StateError] if none
  /// is registered. Prefer this in host-shell code paths where a
  /// missing mini-program indicates a programming error (for example a
  /// stale deep link) rather than a recoverable user-facing condition.
  MiniProgram getById(String id) {
    final MiniProgram? program = _programs[id];
    if (program == null) {
      throw StateError(
        'No MiniProgram registered with id "$id". '
        'Registered ids: ${_programs.keys.join(', ')}',
      );
    }
    return program;
  }

  /// Whether a mini-program with [id] is currently registered.
  bool contains(String id) => _programs.containsKey(id);
}
