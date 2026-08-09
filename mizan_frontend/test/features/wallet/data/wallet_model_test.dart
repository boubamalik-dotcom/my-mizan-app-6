import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/features/wallet/data/wallet_model.dart';

void main() {
  group('WalletModel.fromJson', () {
    const Map<String, dynamic> baseJson = <String, dynamic>{
      'wallet_id': 'wallet-1',
      'user_id': 'user-1',
      'currency': 'DZD',
      'is_locked': false,
      'version': 1,
    };

    test('parses an integer balance', () {
      final WalletModel wallet = WalletModel.fromJson(<String, dynamic>{
        ...baseJson,
        'balance': 15000,
      });

      expect(wallet.walletId, 'wallet-1');
      expect(wallet.userId, 'user-1');
      expect(wallet.balance, 15000.0);
      expect(wallet.currency, 'DZD');
      expect(wallet.isLocked, isFalse);
      expect(wallet.version, 1);
    });

    test('parses a decimal balance', () {
      final WalletModel wallet = WalletModel.fromJson(<String, dynamic>{
        ...baseJson,
        'balance': 15000.5,
      });

      expect(wallet.balance, 15000.5);
    });

    test('parses a numeric-string balance (defensive fallback)', () {
      final WalletModel wallet = WalletModel.fromJson(<String, dynamic>{
        ...baseJson,
        'balance': '2500.75',
      });

      expect(wallet.balance, 2500.75);
    });

    test('parses a locked wallet', () {
      final WalletModel wallet = WalletModel.fromJson(<String, dynamic>{
        ...baseJson,
        'balance': 0,
        'is_locked': true,
      });

      expect(wallet.isLocked, isTrue);
    });

    test('throws a FormatException for a non-numeric balance', () {
      expect(
        () => WalletModel.fromJson(<String, dynamic>{
          ...baseJson,
          'balance': <String, dynamic>{'unexpected': 'shape'},
        }),
        throwsA(isA<FormatException>()),
      );
    });
  });
}
