import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/shared/utils/validators.dart';

void main() {
  group('amount', () {
    test('accepts positive figures, with or without decimals', () {
      expect(Validators.amount('150'), isNull);
      expect(Validators.amount('150.75'), isNull);
      expect(Validators.amount(' 0.01 '), isNull);
      // The Arabic decimal separator is accepted too.
      expect(Validators.amount('150٫5'), isNull);
    });

    test('requires a value', () {
      expect(Validators.amount(null), 'المبلغ مطلوب.');
      expect(Validators.amount('   '), 'المبلغ مطلوب.');
    });

    test('rejects non-numeric input', () {
      expect(Validators.amount('abc'), 'يرجى إدخال مبلغ رقمي صالح.');
      expect(Validators.amount('1.2.3'), 'يرجى إدخال مبلغ رقمي صالح.');
    });

    test('rejects zero and negatives, mirroring the backend gt=0 rule', () {
      expect(Validators.amount('0'), 'يجب أن يكون المبلغ أكبر من صفر.');
      expect(Validators.amount('-5'), 'يجب أن يكون المبلغ أكبر من صفر.');
    });
  });

  group('walletId', () {
    test('only requires that something was entered', () {
      expect(Validators.walletId('wallet-2'), isNull);
      expect(Validators.walletId(''), 'معرّف المحفظة مطلوب.');
    });
  });

  group('Validators.email', () {
    test('rejects an empty value', () {
      expect(Validators.email(''), isNotNull);
      expect(Validators.email(null), isNotNull);
    });

    test('rejects an obviously malformed address', () {
      expect(Validators.email('not-an-email'), isNotNull);
      expect(Validators.email('missing-domain@'), isNotNull);
    });

    test('accepts a well-formed address', () {
      expect(Validators.email('alice@example.com'), isNull);
    });
  });

  group('Validators.loginPassword', () {
    test('rejects an empty value', () {
      expect(Validators.loginPassword(''), isNotNull);
    });

    test('accepts any non-empty value, regardless of length', () {
      expect(Validators.loginPassword('x'), isNull);
    });
  });

  group('Validators.newPassword', () {
    test('rejects an empty value', () {
      expect(Validators.newPassword(''), isNotNull);
    });

    test('rejects a value shorter than the backend minimum', () {
      expect(Validators.newPassword('short'), isNotNull);
    });

    test('accepts a value meeting the backend minimum length', () {
      expect(
          Validators.newPassword('a' * Validators.minPasswordLength), isNull);
    });
  });

  group('Validators.fullName', () {
    test('rejects an empty value', () {
      expect(Validators.fullName('   '), isNotNull);
    });

    test('accepts a non-empty value', () {
      expect(Validators.fullName('Alice Example'), isNull);
    });
  });
}
