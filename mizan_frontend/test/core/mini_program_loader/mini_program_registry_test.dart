import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/core/mini_program_loader/mini_program_base.dart';
import 'package:mizan_frontend/core/mini_program_loader/mini_program_registry.dart';

class _FakeMiniProgram extends BaseMiniProgram {
  _FakeMiniProgram(this.id);

  @override
  final String id;

  @override
  String get title => 'Fake $id';

  @override
  String get description => 'A fake mini-program for tests';

  @override
  IconData get icon => Icons.extension_outlined;

  @override
  Color get accentColor => Colors.grey;

  @override
  Widget buildRootWidget(BuildContext context) => const SizedBox.shrink();
}

void main() {
  group('MiniProgramRegistry.instance (app composition root)', () {
    test('registers the three shipped mini-programs by id', () {
      final MiniProgramRegistry registry = MiniProgramRegistry.instance;

      expect(registry.programs.length, 3);
      expect(registry.contains('tawazun_freight_ai'), isTrue);
      expect(registry.contains('mizan_door'), isTrue);
      expect(registry.contains('oran_real_estate'), isTrue);
    });

    test('getById returns the matching mini-program', () {
      final MiniProgram program =
          MiniProgramRegistry.instance.getById('mizan_door');
      expect(program.id, 'mizan_door');
    });

    test('getById throws StateError for an unknown id', () {
      expect(
        () => MiniProgramRegistry.instance.getById('does_not_exist'),
        throwsA(isA<StateError>()),
      );
    });

    test('find returns null for an unknown id', () {
      expect(MiniProgramRegistry.instance.find('does_not_exist'), isNull);
    });
  });

  group('MiniProgramRegistry.forTesting (isolated registry)', () {
    test('starts empty and can register fake mini-programs', () {
      final MiniProgramRegistry registry = MiniProgramRegistry.forTesting();
      expect(registry.programs, isEmpty);

      registry.registerAll(<MiniProgram>[
        _FakeMiniProgram('alpha'),
        _FakeMiniProgram('beta'),
      ]);

      expect(registry.programs.length, 2);
      expect(registry.getById('alpha').id, 'alpha');
    });

    test('register replaces an existing entry with the same id', () {
      final MiniProgramRegistry registry = MiniProgramRegistry.forTesting();
      final _FakeMiniProgram first = _FakeMiniProgram('dup');
      final _FakeMiniProgram second = _FakeMiniProgram('dup');

      registry.register(first);
      registry.register(second);

      expect(registry.programs.length, 1);
      expect(registry.getById('dup'), same(second));
    });

    test('unregister removes a mini-program', () {
      final MiniProgramRegistry registry = MiniProgramRegistry.forTesting();
      registry.register(_FakeMiniProgram('temp'));
      expect(registry.contains('temp'), isTrue);

      registry.unregister('temp');
      expect(registry.contains('temp'), isFalse);
    });
  });
}
