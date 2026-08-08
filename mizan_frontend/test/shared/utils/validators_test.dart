import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/shared/utils/validators.dart';

void main() {
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
