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
}
