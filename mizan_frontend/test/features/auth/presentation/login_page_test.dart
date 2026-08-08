import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/core/core_navigator.dart';
import 'package:mizan_frontend/features/auth/data/auth_repository.dart';
import 'package:mizan_frontend/features/auth/presentation/pages/login_page.dart';
import 'package:mizan_frontend/features/auth/presentation/pages/register_page.dart';
import 'package:mizan_frontend/shared/exceptions/network_exception.dart';
import 'package:mizan_frontend/shared/network/interceptors.dart'
    show LoginRedirectReason;
import 'package:mocktail/mocktail.dart';

class MockAuthRepository extends Mock implements AuthRepository {}

void main() {
  late MockAuthRepository authRepository;

  setUp(() {
    authRepository = MockAuthRepository();
  });

  /// A minimal `MaterialApp` with just enough routing for [LoginPage]
  /// to navigate: the login route itself, a stand-in dashboard, and a
  /// real [RegisterPage] (wired with the same mock repository) so the
  /// "إنشاء حساب" link can be exercised too.
  Widget buildTestApp() {
    return MaterialApp(
      initialRoute: CoreRoutes.login,
      onGenerateRoute: (RouteSettings settings) {
        switch (settings.name) {
          case CoreRoutes.login:
            return MaterialPageRoute<void>(
              settings: settings,
              builder: (_) => LoginPage(authRepository: authRepository),
            );
          case CoreRoutes.register:
            return MaterialPageRoute<void>(
              settings: settings,
              builder: (_) => RegisterPage(authRepository: authRepository),
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

  group('LoginPage', () {
    testWidgets(
        'shows validation errors and never calls login for an empty form',
        (WidgetTester tester) async {
      when(() => authRepository.isLoggedIn()).thenAnswer((_) async => false);

      await tester.pumpWidget(buildTestApp());
      await tester.pumpAndSettle();

      await tester.tap(find.widgetWithText(ElevatedButton, 'دخول'));
      await tester.pump();

      expect(find.text('البريد الإلكتروني مطلوب.'), findsOneWidget);
      expect(find.text('كلمة المرور مطلوبة.'), findsOneWidget);
      verifyNever(
        () => authRepository.login(
          email: any(named: 'email'),
          password: any(named: 'password'),
        ),
      );
    });

    testWidgets('navigates to the dashboard on successful login',
        (WidgetTester tester) async {
      when(() => authRepository.isLoggedIn()).thenAnswer((_) async => false);
      when(
        () => authRepository.login(
          email: any(named: 'email'),
          password: any(named: 'password'),
        ),
      ).thenAnswer((_) async {});

      await tester.pumpWidget(buildTestApp());
      await tester.pumpAndSettle();

      await tester.enterText(
        find.byType(TextFormField).at(0),
        'alice@example.com',
      );
      await tester.enterText(
          find.byType(TextFormField).at(1), 'correct-password');
      await tester.tap(find.widgetWithText(ElevatedButton, 'دخول'));
      await tester.pumpAndSettle();

      expect(find.text('DASHBOARD_PAGE'), findsOneWidget);
      verify(
        () => authRepository.login(
          email: 'alice@example.com',
          password: 'correct-password',
        ),
      ).called(1);
    });

    testWidgets('shows the backend error message in a SnackBar on failure',
        (WidgetTester tester) async {
      when(() => authRepository.isLoggedIn()).thenAnswer((_) async => false);
      when(
        () => authRepository.login(
          email: any(named: 'email'),
          password: any(named: 'password'),
        ),
      ).thenThrow(
        const NetworkException(
          'البريد الإلكتروني أو كلمة المرور غير صحيحة.',
          statusCode: 401,
        ),
      );

      await tester.pumpWidget(buildTestApp());
      await tester.pumpAndSettle();

      await tester.enterText(
        find.byType(TextFormField).at(0),
        'alice@example.com',
      );
      await tester.enterText(
          find.byType(TextFormField).at(1), 'wrong-password');
      await tester.tap(find.widgetWithText(ElevatedButton, 'دخول'));
      await tester.pumpAndSettle();

      expect(
        find.text('البريد الإلكتروني أو كلمة المرور غير صحيحة.'),
        findsOneWidget,
      );
      // Still on the login page — the failure must not navigate away.
      expect(find.byType(LoginPage), findsOneWidget);
    });

    testWidgets(
        'skips straight to the dashboard when a session is already stored',
        (WidgetTester tester) async {
      when(() => authRepository.isLoggedIn()).thenAnswer((_) async => true);

      await tester.pumpWidget(buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('DASHBOARD_PAGE'), findsOneWidget);
      expect(find.byType(LoginPage), findsNothing);
    });

    testWidgets('the "إنشاء حساب" button navigates to RegisterPage',
        (WidgetTester tester) async {
      when(() => authRepository.isLoggedIn()).thenAnswer((_) async => false);

      await tester.pumpWidget(buildTestApp());
      await tester.pumpAndSettle();

      await tester.tap(find.text('إنشاء حساب'));
      await tester.pumpAndSettle();

      expect(find.byType(RegisterPage), findsOneWidget);
    });

    testWidgets(
        'shows a session-expired notice when redirected with that reason',
        (WidgetTester tester) async {
      when(() => authRepository.isLoggedIn()).thenAnswer((_) async => false);

      final GlobalKey<NavigatorState> navigatorKey =
          GlobalKey<NavigatorState>();
      await tester.pumpWidget(
        MaterialApp(
          navigatorKey: navigatorKey,
          initialRoute: '/blank',
          onGenerateRoute: (RouteSettings settings) {
            if (settings.name == CoreRoutes.login) {
              return MaterialPageRoute<void>(
                settings: settings,
                builder: (_) => LoginPage(authRepository: authRepository),
              );
            }
            return MaterialPageRoute<void>(
              settings: settings,
              builder: (_) => const SizedBox.shrink(),
            );
          },
        ),
      );
      await tester.pumpAndSettle();

      navigatorKey.currentState!.pushNamedAndRemoveUntil(
        CoreRoutes.login,
        (Route<dynamic> route) => false,
        arguments: LoginRedirectReason.sessionExpired,
      );
      await tester.pumpAndSettle();

      expect(
        find.text('انتهت صلاحية الجلسة. يرجى تسجيل الدخول مرة أخرى.'),
        findsOneWidget,
      );
    });
  });
}
