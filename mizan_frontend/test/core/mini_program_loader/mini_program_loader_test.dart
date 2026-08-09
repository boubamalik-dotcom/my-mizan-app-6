import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/core/mini_program_loader/mini_program_base.dart';
import 'package:mizan_frontend/core/mini_program_loader/mini_program_loader.dart';
import 'package:mizan_frontend/core/mini_program_loader/mini_program_registry.dart';

/// A fake mini-program that records how many times it was initialized
/// and disposed, so tests can assert on the loader's lifecycle
/// management without depending on any real mini-program.
class _CountingMiniProgram extends BaseMiniProgram {
  _CountingMiniProgram(this.id);

  @override
  final String id;

  int initializeCount = 0;
  int disposeCount = 0;

  @override
  String get title => 'Counting $id';

  @override
  String get description => 'Counts lifecycle calls';

  @override
  IconData get icon => Icons.science_outlined;

  @override
  Color get accentColor => Colors.teal;

  @override
  Future<void> initialize() async {
    initializeCount++;
    await super.initialize();
  }

  @override
  Future<void> dispose() async {
    disposeCount++;
    await super.dispose();
  }

  @override
  Widget buildRootWidget(BuildContext context) => const SizedBox.shrink();
}

void main() {
  late MiniProgramRegistry registry;
  late MiniProgramLoader loader;
  late _CountingMiniProgram a;
  late _CountingMiniProgram b;
  late _CountingMiniProgram c;

  setUp(() {
    registry = MiniProgramRegistry.forTesting();
    a = _CountingMiniProgram('a');
    b = _CountingMiniProgram('b');
    c = _CountingMiniProgram('c');
    registry.registerAll(<MiniProgram>[a, b, c]);
    loader = MiniProgramLoader(registry: registry, maxCachedPrograms: 2);
  });

  test('load() initializes a mini-program exactly once', () async {
    expect(a.isInitialized, isFalse);

    final MiniProgram first = await loader.load('a');
    final MiniProgram second = await loader.load('a');

    expect(first, same(second));
    expect(a.initializeCount, 1);
    expect(a.isInitialized, isTrue);
  });

  test('load() throws for an id that is not registered', () {
    expect(() => loader.load('missing'), throwsA(isA<StateError>()));
  });

  test('loader stays under maxCachedPrograms via LRU eviction', () async {
    await loader.load('a');
    await loader.load('b');
    expect(loader.loadedPrograms.length, 2);

    // Loading a third mini-program should evict the least-recently-used
    // one ("a") to respect maxCachedPrograms == 2.
    await loader.load('c');

    expect(loader.loadedPrograms.length, 2);
    expect(loader.isLoaded('a'), isFalse);
    expect(loader.isLoaded('b'), isTrue);
    expect(loader.isLoaded('c'), isTrue);
    expect(a.disposeCount, 1);
  });

  test('re-accessing a loaded mini-program refreshes its recency', () async {
    await loader.load('a');
    await loader.load('b');
    // Touch "a" again so "b" becomes the least-recently-used entry.
    await loader.load('a');
    await loader.load('c');

    expect(loader.isLoaded('a'), isTrue);
    expect(loader.isLoaded('b'), isFalse);
    expect(loader.isLoaded('c'), isTrue);
    expect(b.disposeCount, 1);
  });

  test('unload() disposes a specific mini-program on demand', () async {
    await loader.load('a');
    expect(loader.isLoaded('a'), isTrue);

    await loader.unload('a');

    expect(loader.isLoaded('a'), isFalse);
    expect(a.disposeCount, 1);
    expect(a.isInitialized, isFalse);
  });

  test('unloadAll() disposes every loaded mini-program', () async {
    await loader.load('a');
    await loader.load('b');

    await loader.unloadAll();

    expect(loader.loadedPrograms, isEmpty);
    expect(a.disposeCount, 1);
    expect(b.disposeCount, 1);
  });

  test('isLoading reflects an in-flight initialize() call', () async {
    expect(loader.isLoading, isFalse);
    final Future<MiniProgram> future = loader.load('a');
    expect(loader.isLoading, isTrue);
    expect(loader.loadingId, 'a');
    await future;
    expect(loader.isLoading, isFalse);
  });
}
