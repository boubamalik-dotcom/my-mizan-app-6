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

  group('money operations', () {
    const WalletModel refreshedWallet = WalletModel(
      walletId: 'wallet-1',
      userId: 'user-1',
      balance: 15150,
      currency: 'DZD',
      isLocked: false,
      version: 2,
    );

    setUp(() {
      when(() => repository.getOrCreateWallet())
          .thenAnswer((_) async => _testWallet);
    });

    test(
        'deposit marks the operation in progress, then re-reads the wallet '
        'from the server rather than adjusting the balance locally', () async {
      when(
        () => repository.deposit(
          walletId: any(named: 'walletId'),
          amount: any(named: 'amount'),
        ),
      ).thenAnswer((_) async => 15150);
      await cubit.loadWalletData();

      final List<WalletState> emitted = <WalletState>[];
      final Future<void> collect = cubit.stream.forEach(emitted.add);

      when(() => repository.getOrCreateWallet())
          .thenAnswer((_) async => refreshedWallet);
      await cubit.deposit(150);
      await cubit.close();
      await collect;

      expect(emitted, <Matcher>[
        isA<WalletOperationInProgress>().having(
          (WalletState s) => (s as WalletOperationInProgress).operation,
          'operation',
          WalletOperation.deposit,
        ),
        isA<WalletLoading>(),
        isA<WalletLoaded>().having(
          (WalletState s) => (s as WalletLoaded).wallet.balance,
          'balance',
          15150,
        ),
      ]);
      verify(() => repository.deposit(walletId: 'wallet-1', amount: 150))
          .called(1);
    });

    test('withdraw passes the loaded wallet id through', () async {
      when(
        () => repository.withdraw(
          walletId: any(named: 'walletId'),
          amount: any(named: 'amount'),
        ),
      ).thenAnswer((_) async => 14850);
      await cubit.loadWalletData();

      await cubit.withdraw(150);

      verify(() => repository.withdraw(walletId: 'wallet-1', amount: 150))
          .called(1);
      // The initial load plus the post-transaction refresh.
      verify(() => repository.getOrCreateWallet()).called(2);
    });

    test('transfer sends the destination wallet id', () async {
      when(
        () => repository.transfer(
          sourceWalletId: any(named: 'sourceWalletId'),
          destinationWalletId: any(named: 'destinationWalletId'),
          amount: any(named: 'amount'),
        ),
      ).thenAnswer((_) async => 14000);
      await cubit.loadWalletData();

      await cubit.transfer(destinationWalletId: 'wallet-2', amount: 1000);

      verify(
        () => repository.transfer(
          sourceWalletId: 'wallet-1',
          destinationWalletId: 'wallet-2',
          amount: 1000,
        ),
      ).called(1);
    });

    test(
        'a rejected transaction restores the previous balance and rethrows so '
        'the sheet can surface the message', () async {
      when(
        () => repository.withdraw(
          walletId: any(named: 'walletId'),
          amount: any(named: 'amount'),
        ),
      ).thenThrow(
        const NetworkException('الرصيد غير كافٍ لإتمام هذه العملية.'),
      );
      await cubit.loadWalletData();

      await expectLater(
        () => cubit.withdraw(999999),
        throwsA(
          isA<NetworkException>().having(
            (NetworkException e) => e.message,
            'message',
            contains('الرصيد غير كافٍ'),
          ),
        ),
      );

      expect(cubit.state, isA<WalletLoaded>());
      expect((cubit.state as WalletLoaded).wallet.balance, _testWallet.balance);
      // A rejected transaction must not trigger a pointless refresh.
      verify(() => repository.getOrCreateWallet()).called(1);
    });

    test('an unexpected failure surfaces a display-ready Arabic message',
        () async {
      when(
        () => repository.deposit(
          walletId: any(named: 'walletId'),
          amount: any(named: 'amount'),
        ),
      ).thenThrow(StateError('boom'));
      await cubit.loadWalletData();

      await expectLater(
        () => cubit.deposit(10),
        throwsA(isA<WalletOperationFailed>()),
      );
      expect(cubit.state, isA<WalletLoaded>());
    });

    test('operating before the wallet has loaded is reported, not attempted',
        () async {
      await expectLater(
        () => cubit.deposit(10),
        throwsA(isA<WalletOperationUnavailable>()),
      );

      verifyNever(
        () => repository.deposit(
          walletId: any(named: 'walletId'),
          amount: any(named: 'amount'),
        ),
      );
      expect(cubit.state, isA<WalletInitial>());
    });
  });
}
