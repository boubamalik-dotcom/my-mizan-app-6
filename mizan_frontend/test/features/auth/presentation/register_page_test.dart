import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/core/core_navigator.dart';
import 'package:mizan_frontend/features/auth/data/auth_repository.dart';
import 'package:mizan_frontend/features/auth/domain/entities/auth_user.dart';
import 'package:mizan_frontend/features/auth/presentation/pages/login_page.dart';
import 'package:mizan_frontend/features/auth/presentation/pages/register_page.dart';
import 'package:mizan_frontend/shared/exceptions/network_exception.dart';
import 'package:mocktail/mocktail.dart';

class MockAuthRepository extends Mock implements AuthRepository {}

void main() {
  late MockAuthRepository authRepository;

  setUp(() {
    authRepository = MockAuthRepository();
  });

  Widget buildTestApp() {
    return MaterialApp(
      initialRoute: CoreRoutes.register,
      onGenerateRoute: (RouteSettings settings) {
        switch (settings.name) {
          case CoreRoutes.register:
            return MaterialPageRoute<void>(
              settings: settings,
              builder: (_) => RegisterPage(authRepository: authRepository),
            );
          case CoreRoutes.login:
            return MaterialPageRoute<void>(
              settings: settings,
              builder: (_) => LoginPage(authRepository: authRepository),
            );
          case CoreRoutes.dashboard:
            return MaterialPageRoute<void>(
              settings: settings,
              builder: (_) => const Scaffold(body: Text('DASHBOARD_PAGE')),
            );
          default:
            return MaterialPageRoute<void>(
              settings: settings,
              builder: (_) => const SizedBox.shrink(),
            );
        }
      },
    );
  }

  Future<void> fillForm(
    WidgetTester tester, {
    String fullName = 'Alice Example',
    String email = 'alice@example.com',
    String password = 'correct-horse-battery-staple',
  }) async {
    await tester.enterText(find.byType(TextFormField).at(0), fullName);
    await tester.enterText(find.byType(TextFormField).at(1), email);
    await tester.enterText(find.byType(TextFormField).at(2), password);
  }

  group('RegisterPage', () {
    testWidgets(
        'shows validation errors and never calls register for an '
        'empty form', (WidgetTester tester) async {
      await tester.pumpWidget(buildTestApp());
      await tester.pumpAndSettle();

      await tester.tap(find.widgetWithText(ElevatedButton, 'إنشاء حساب'));
      await tester.pump();

      expect(find.text('الاسم الكامل مطلوب.'), findsOneWidget);
      expect(find.text('البريد الإلكتروني مطلوب.'), findsOneWidget);
      expect(find.text('كلمة المرور مطلوبة.'), findsOneWidget);
      verifyNever(
        () => authRepository.register(
          fullName: any(named: 'fullName'),
          email: any(named: 'email'),
          password: any(named: 'password'),
        ),
      );
    });

    testWidgets('rejects a password shorter than the backend minimum',
        (WidgetTester tester) async {
      await tester.pumpWidget(buildTestApp());
      await tester.pumpAndSettle();

      await fillForm(tester, password: 'short');
      await tester.tap(find.widgetWithText(ElevatedButton, 'إنشاء حساب'));
      await tester.pump();

      expect(find.text('يجب ألا تقل كلمة المرور عن 8 أحرف.'), findsOneWidget);
      verifyNever(
        () => authRepository.register(
          fullName: any(named: 'fullName'),
          email: any(named: 'email'),
          password: any(named: 'password'),
        ),
      );
    });

    testWidgets(
        'registers, immediately logs in, and lands on the dashboard on success',
        (WidgetTester tester) async {
      when(
        () => authRepository.register(
          fullName: any(named: 'fullName'),
          email: any(named: 'email'),
          password: any(named: 'password'),
        ),
      ).thenAnswer(
        (_) async => const AuthUser(
          id: 'user-1',
          email: 'alice@example.com',
          fullName: 'Alice Example',
          isActive: true,
        ),
      );
      when(
        () => authRepository.login(
          email: any(named: 'email'),
          password: any(named: 'password'),
        ),
      ).thenAnswer((_) async {});

      await tester.pumpWidget(buildTestApp());
      await tester.pumpAndSettle();

      await fillForm(tester);
      await tester.tap(find.widgetWithText(ElevatedButton, 'إنشاء حساب'));
      await tester.pumpAndSettle();

      expect(find.text('DASHBOARD_PAGE'), findsOneWidget);
      verify(
        () => authRepository.register(
          fullName: 'Alice Example',
          email: 'alice@example.com',
          password: 'correct-horse-battery-staple',
        ),
      ).called(1);
      verify(
        () => authRepository.login(
          email: 'alice@example.com',
          password: 'correct-horse-battery-staple',
        ),
      ).called(1);
    });

    testWidgets(
        'shows the backend error message on a failed registration '
        'and never attempts to log in', (WidgetTester tester) async {
      when(
        () => authRepository.register(
          fullName: any(named: 'fullName'),
          email: any(named: 'email'),
          password: any(named: 'password'),
        ),
      ).thenThrow(
        const NetworkException(
          'هذا البريد الإلكتروني مسجّل بالفعل. يرجى تسجيل الدخول بدلاً من ذلك.',
          statusCode: 400,
        ),
      );

      await tester.pumpWidget(buildTestApp());
      await tester.pumpAndSettle();

      await fillForm(tester);
      await tester.tap(find.widgetWithText(ElevatedButton, 'إنشاء حساب'));
      await tester.pumpAndSettle();

      expect(
        find.text(
            'هذا البريد الإلكتروني مسجّل بالفعل. يرجى تسجيل الدخول بدلاً من ذلك.'),
        findsOneWidget,
      );
      expect(find.byType(RegisterPage), findsOneWidget);
      verifyNever(
        () => authRepository.login(
          email: any(named: 'email'),
          password: any(named: 'password'),
        ),
      );
    });

    testWidgets(
        'falls back to the login page with a success notice if the '
        'automatic post-registration login fails', (WidgetTester tester) async {
      when(
        () => authRepository.register(
          fullName: any(named: 'fullName'),
          email: any(named: 'email'),
          password: any(named: 'password'),
        ),
      ).thenAnswer(
        (_) async => const AuthUser(
          id: 'user-1',
          email: 'alice@example.com',
          fullName: 'Alice Example',
          isActive: true,
        ),
      );
      when(
        () => authRepository.login(
          email: any(named: 'email'),
          password: any(named: 'password'),
        ),
      ).thenThrow(const NetworkException('تعذّر الاتصال بالخادم.'));
      when(() => authRepository.isLoggedIn()).thenAnswer((_) async => false);

      await tester.pumpWidget(buildTestApp());
      await tester.pumpAndSettle();

      await fillForm(tester);
      await tester.tap(find.widgetWithText(ElevatedButton, 'إنشاء حساب'));
      await tester.pumpAndSettle();

      expect(find.byType(LoginPage), findsOneWidget);
      expect(
        find.text('تم إنشاء حسابك بنجاح. يرجى تسجيل الدخول.'),
        findsOneWidget,
      );
    });
  });
}
