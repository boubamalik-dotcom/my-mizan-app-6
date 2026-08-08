import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/features/wallet/data/wallet_model.dart';
import 'package:mizan_frontend/features/wallet/data/wallet_repository.dart';
import 'package:mizan_frontend/features/wallet/presentation/state/wallet_cubit.dart';
import 'package:mizan_frontend/features/wallet/presentation/state/wallet_state.dart';
import 'package:mizan_frontend/shared/exceptions/network_exception.dart';
import 'package:mocktail/mocktail.dart';

class MockWalletRepository extends Mock implements WalletRepository {}

const WalletModel _testWallet = WalletModel(
  walletId: 'wallet-1',
  userId: 'user-1',
  balance: 15000,
  currency: 'DZD',
  isLocked: false,
  version: 1,
);

void main() {
  late MockWalletRepository repository;
  late WalletCubit cubit;

  setUp(() {
    repository = MockWalletRepository();
    cubit = WalletCubit(repository: repository);
  });

  tearDown(() => cubit.close());

  test('starts in WalletInitial', () {
    expect(cubit.state, isA<WalletInitial>());
  });

  test('loadWalletData() emits [WalletLoading, WalletLoaded] on success',
      () async {
    when(() => repository.getOrCreateWallet())
        .thenAnswer((_) async => _testWallet);

    final List<WalletState> emitted = <WalletState>[];
    final Stream<WalletState> subscription = cubit.stream;
    final Future<void> collect = subscription.forEach(emitted.add);

    await cubit.loadWalletData();
    await cubit.close();
    await collect;

    expect(emitted, <Matcher>[
      isA<WalletLoading>(),
      isA<WalletLoaded>().having(
          (WalletState s) => (s as WalletLoaded).wallet, 'wallet', _testWallet),
    ]);
  });

  test(
      'loadWalletData() emits [WalletLoading, WalletError] on failure, '
      'using the exception\'s already-localized message', () async {
    when(() => repository.getOrCreateWallet())
        .thenThrow(const NetworkException('تعذّر الاتصال بالخادم.'));

    final List<WalletState> emitted = <WalletState>[];
    final Future<void> collect = cubit.stream.forEach(emitted.add);

    await cubit.loadWalletData();
    await cubit.close();
    await collect;

    expect(emitted, <Matcher>[
      isA<WalletLoading>(),
      isA<WalletError>().having((WalletState s) => (s as WalletError).message,
          'message', 'تعذّر الاتصال بالخادم.'),
    ]);
  });

  test(
      'loadWalletData() falls back to a generic Arabic message for a '
      'non-AppException failure', () async {
    when(() => repository.getOrCreateWallet())
        .thenThrow(StateError('unexpected'));

    await cubit.loadWalletData();

    expect(cubit.state, isA<WalletError>());
    expect(
      (cubit.state as WalletError).message,
      'حدث خطأ غير متوقع أثناء تحميل المحفظة.',
    );
  });

  test(
      'calling loadWalletData() again after an error retries and can '
      'succeed', () async {
    when(() => repository.getOrCreateWallet())
        .thenThrow(const NetworkException('تعذّر الاتصال بالخادم.'));
    await cubit.loadWalletData();
    expect(cubit.state, isA<WalletError>());

    when(() => repository.getOrCreateWallet())
        .thenAnswer((_) async => _testWallet);
    await cubit.loadWalletData();

    expect(cubit.state, isA<WalletLoaded>());
    expect((cubit.state as WalletLoaded).wallet, _testWallet);
    verify(() => repository.getOrCreateWallet()).called(2);
  });
}
