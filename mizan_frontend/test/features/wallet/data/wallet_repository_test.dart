import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/features/wallet/data/wallet_model.dart';
import 'package:mizan_frontend/features/wallet/data/wallet_remote_data_source.dart';
import 'package:mizan_frontend/features/wallet/data/wallet_repository.dart';
import 'package:mizan_frontend/shared/exceptions/network_exception.dart';
import 'package:mocktail/mocktail.dart';

class MockWalletRemoteDataSource extends Mock
    implements WalletRemoteDataSource {}

const WalletModel _existingWallet = WalletModel(
  walletId: 'wallet-1',
  userId: 'user-1',
  balance: 500,
  currency: 'DZD',
  isLocked: false,
  version: 3,
);

const WalletModel _newlyProvisionedWallet = WalletModel(
  walletId: 'wallet-2',
  userId: 'user-1',
  balance: 0,
  currency: 'DZD',
  isLocked: false,
  version: 1,
);

DioException _dioError({required int statusCode, dynamic data}) {
  final RequestOptions requestOptions = RequestOptions(path: '/wallet');
  return DioException(
    requestOptions: requestOptions,
    type: DioExceptionType.badResponse,
    response: Response<dynamic>(
      requestOptions: requestOptions,
      statusCode: statusCode,
      data: data,
    ),
  );
}

void main() {
  late MockWalletRemoteDataSource remoteDataSource;
  late WalletRepository repository;

  setUp(() {
    remoteDataSource = MockWalletRemoteDataSource();
    repository = WalletRepository(remoteDataSource: remoteDataSource);
  });

  group('getOrCreateWallet', () {
    test('returns the wallet from GET /wallet when one already exists',
        () async {
      when(() => remoteDataSource.fetchWallet())
          .thenAnswer((_) async => _existingWallet);

      final WalletModel result = await repository.getOrCreateWallet();

      expect(result, _existingWallet);
      verifyNever(() => remoteDataSource.createWallet());
    });

    test(
        'auto-provisions via POST /wallet when GET /wallet returns 404, and '
        'returns the newly created wallet', () async {
      when(() => remoteDataSource.fetchWallet())
          .thenThrow(_dioError(statusCode: 404));
      when(() => remoteDataSource.createWallet())
          .thenAnswer((_) async => _newlyProvisionedWallet);

      final WalletModel result = await repository.getOrCreateWallet();

      expect(result, _newlyProvisionedWallet);
      verify(() => remoteDataSource.fetchWallet()).called(1);
      verify(() => remoteDataSource.createWallet()).called(1);
    });

    test('propagates a non-404 GET failure without attempting to provision',
        () async {
      when(() => remoteDataSource.fetchWallet())
          .thenThrow(_dioError(statusCode: 500));

      await expectLater(
        () => repository.getOrCreateWallet(),
        throwsA(isA<NetworkException>()),
      );
      verifyNever(() => remoteDataSource.createWallet());
    });

    test('propagates a failure from the provisioning call itself', () async {
      when(() => remoteDataSource.fetchWallet())
          .thenThrow(_dioError(statusCode: 404));
      when(() => remoteDataSource.createWallet())
          .thenThrow(_dioError(statusCode: 500));

      await expectLater(
        () => repository.getOrCreateWallet(),
        throwsA(isA<NetworkException>()),
      );
    });

    test(
        'a connection error (not a DioException 404) is not treated as '
        '"no wallet yet"', () async {
      when(() => remoteDataSource.fetchWallet()).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/wallet'),
          type: DioExceptionType.connectionError,
        ),
      );

      await expectLater(
        () => repository.getOrCreateWallet(),
        throwsA(isA<NetworkException>()),
      );
      verifyNever(() => remoteDataSource.createWallet());
    });
  });

  group('money operations', () {
    test(
        'deposit forwards the wallet id and amount, returning the new balance '
        'the backend reported', () async {
      when(
        () => remoteDataSource.deposit(
          walletId: any(named: 'walletId'),
          amount: any(named: 'amount'),
        ),
      ).thenAnswer((_) async => 650);

      final double balance = await repository.deposit(
        walletId: 'wallet-1',
        amount: 150,
      );

      expect(balance, 650);
      verify(
        () => remoteDataSource.deposit(walletId: 'wallet-1', amount: 150),
      ).called(1);
    });

    test('withdraw forwards the wallet id and amount', () async {
      when(
        () => remoteDataSource.withdraw(
          walletId: any(named: 'walletId'),
          amount: any(named: 'amount'),
        ),
      ).thenAnswer((_) async => 350);

      final double balance = await repository.withdraw(
        walletId: 'wallet-1',
        amount: 150,
      );

      expect(balance, 350);
      verify(
        () => remoteDataSource.withdraw(walletId: 'wallet-1', amount: 150),
      ).called(1);
    });

    test(
        "transfer sends both wallet ids, returning the source wallet's new "
        'balance', () async {
      when(
        () => remoteDataSource.transfer(
          sourceWalletId: any(named: 'sourceWalletId'),
          destinationWalletId: any(named: 'destinationWalletId'),
          amount: any(named: 'amount'),
        ),
      ).thenAnswer((_) async => 400);

      final double balance = await repository.transfer(
        sourceWalletId: 'wallet-1',
        destinationWalletId: 'wallet-2',
        amount: 100,
      );

      expect(balance, 400);
      verify(
        () => remoteDataSource.transfer(
          sourceWalletId: 'wallet-1',
          destinationWalletId: 'wallet-2',
          amount: 100,
        ),
      ).called(1);
    });
  });

  group('transaction error mapping', () {
    /// Each status code the backend's wallet controller can return for
    /// a money operation gets its own precise Arabic message, so a
    /// rejected transaction tells the user what actually happened.
    const Map<int, String> expectedFragments = <int, String>{
      400: 'الرصيد غير كافٍ',
      403: 'لا تملك صلاحية',
      404: 'لم يتم العثور على المحفظة',
      409: 'تم تعديل المحفظة',
      422: 'المبلغ المدخل غير صالح',
      423: 'مقفلة',
    };

    for (final MapEntry<int, String> entry in expectedFragments.entries) {
      test('maps ${entry.key} to its own Arabic message', () async {
        when(
          () => remoteDataSource.deposit(
            walletId: any(named: 'walletId'),
            amount: any(named: 'amount'),
          ),
        ).thenThrow(_dioError(statusCode: entry.key));

        await expectLater(
          () => repository.deposit(walletId: 'wallet-1', amount: 10),
          throwsA(
            isA<NetworkException>()
                .having(
                  (NetworkException e) => e.statusCode,
                  'statusCode',
                  entry.key,
                )
                .having(
                  (NetworkException e) => e.message,
                  'message',
                  contains(entry.value),
                ),
          ),
        );
      });
    }

    test('falls back to the generic mapping for a 500', () async {
      when(
        () => remoteDataSource.withdraw(
          walletId: any(named: 'walletId'),
          amount: any(named: 'amount'),
        ),
      ).thenThrow(_dioError(statusCode: 500));

      await expectLater(
        () => repository.withdraw(walletId: 'wallet-1', amount: 10),
        throwsA(
          isA<NetworkException>()
              .having((NetworkException e) => e.statusCode, 'statusCode', 500),
        ),
      );
    });

    test('falls back to the generic mapping when offline', () async {
      when(
        () => remoteDataSource.transfer(
          sourceWalletId: any(named: 'sourceWalletId'),
          destinationWalletId: any(named: 'destinationWalletId'),
          amount: any(named: 'amount'),
        ),
      ).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/wallet/transfer'),
          type: DioExceptionType.connectionError,
        ),
      );

      await expectLater(
        () => repository.transfer(
          sourceWalletId: 'wallet-1',
          destinationWalletId: 'wallet-2',
          amount: 10,
        ),
        throwsA(
          isA<NetworkException>()
              .having((NetworkException e) => e.statusCode, 'statusCode', null),
        ),
      );
    });
  });

  group('WalletRemoteDataSource.formatAmount', () {
    test('serializes money as an exact decimal string, not a float', () {
      // `0.1 + 0.2` is 0.30000000000000004 as a double; that must never
      // reach a ledger that stores exact decimals.
      expect(WalletRemoteDataSource.formatAmount(0.1 + 0.2), '0.3');
      expect(WalletRemoteDataSource.formatAmount(15000), '15000');
      expect(WalletRemoteDataSource.formatAmount(15000.5), '15000.5');
      expect(WalletRemoteDataSource.formatAmount(0.0001), '0.0001');
    });
  });
}
