import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/features/wallet/data/wallet_model.dart';
import 'package:mizan_frontend/features/wallet/data/wallet_repository.dart';
import 'package:mizan_frontend/features/wallet/presentation/pages/wallet_details_page.dart';
import 'package:mizan_frontend/features/wallet/presentation/state/wallet_cubit.dart';
import 'package:mizan_frontend/shared/design_system/theme/app_theme.dart';
import 'package:mizan_frontend/shared/exceptions/network_exception.dart';
import 'package:mocktail/mocktail.dart';

class MockWalletRepository extends Mock implements WalletRepository {}

const WalletModel _wallet = WalletModel(
  walletId: 'wallet-1',
  userId: 'user-1',
  balance: 15000,
  currency: 'DZD',
  isLocked: false,
  version: 3,
);

const WalletModel _walletAfterDeposit = WalletModel(
  walletId: 'wallet-1',
  userId: 'user-1',
  balance: 15150,
  currency: 'DZD',
  isLocked: false,
  version: 4,
);

void main() {
  late MockWalletRepository repository;

  setUp(() {
    repository = MockWalletRepository();
    when(() => repository.getOrCreateWallet()).thenAnswer((_) async => _wallet);
  });

  /// Mounts the page inside the app's real RTL/theme chrome, driving it
  /// with a cubit backed by a mock repository so nothing touches the
  /// network.
  Future<WalletCubit> pumpPage(WidgetTester tester) async {
    final WalletCubit cubit = WalletCubit(repository: repository);
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        locale: const Locale('ar'),
        localizationsDelegates: const <LocalizationsDelegate<dynamic>>[
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: const <Locale>[Locale('ar')],
        home: WalletDetailsPage(walletCubit: cubit),
      ),
    );
    await tester.pumpAndSettle();
    return cubit;
  }

  group('layout', () {
    testWidgets('shows the balance and all three action buttons',
        (WidgetTester tester) async {
      await pumpPage(tester);

      expect(find.text('المحفظة الرقمية'), findsOneWidget);
      expect(find.text('الرصيد الحالي'), findsOneWidget);
      expect(find.text('15,000 DZD'), findsOneWidget);
      expect(find.text('إيداع'), findsOneWidget);
      expect(find.text('سحب'), findsOneWidget);
      expect(find.text('تحويل'), findsOneWidget);
      expect(find.textContaining('رقم المحفظة: wallet-1'), findsOneWidget);
    });

    testWidgets('the three action buttons are exactly equal in width',
        (WidgetTester tester) async {
      await pumpPage(tester);

      final double depositWidth = tester.getSize(find.text('إيداع')).width;
      final List<double> widths = <String>['إيداع', 'سحب', 'تحويل']
          .map((String label) => tester
              .getSize(
                find.ancestor(
                  of: find.text(label),
                  matching: find.byType(InkWell),
                ),
              )
              .width)
          .toList();

      expect(depositWidth, greaterThan(0));
      expect(widths[0], widths[1]);
      expect(widths[1], widths[2]);
    });

    testWidgets('renders right-to-left', (WidgetTester tester) async {
      await pumpPage(tester);

      expect(
        Directionality.of(tester.element(find.text('الرصيد الحالي'))),
        TextDirection.rtl,
      );
    });

    testWidgets('surfaces a load failure with a retry affordance',
        (WidgetTester tester) async {
      when(() => repository.getOrCreateWallet())
          .thenThrow(const NetworkException('تعذّر الاتصال بالخادم.'));

      await pumpPage(tester);

      expect(find.text('تعذّر الاتصال بالخادم.'), findsOneWidget);
      expect(find.text('إعادة المحاولة'), findsOneWidget);

      when(() => repository.getOrCreateWallet())
          .thenAnswer((_) async => _wallet);
      await tester.tap(find.text('إعادة المحاولة'));
      await tester.pumpAndSettle();

      expect(find.text('15,000 DZD'), findsOneWidget);
    });
  });

  group('deposit', () {
    testWidgets(
        'opens a sheet, posts the amount, and refreshes the balance '
        'from the server', (WidgetTester tester) async {
      when(
        () => repository.deposit(
          walletId: any(named: 'walletId'),
          amount: any(named: 'amount'),
        ),
      ).thenAnswer((_) async => 15150);

      await pumpPage(tester);
      await tester.tap(find.text('إيداع'));
      await tester.pumpAndSettle();

      expect(find.text('إيداع رصيد'), findsOneWidget);
      expect(find.text('تأكيد'), findsOneWidget);
      // A deposit needs no destination — that field is transfer-only.
      expect(find.text('معرّف محفظة المستلم'), findsNothing);

      // The refreshed balance must come from the server, not from a
      // locally-added figure.
      when(() => repository.getOrCreateWallet())
          .thenAnswer((_) async => _walletAfterDeposit);

      await tester.enterText(find.byType(TextFormField), '150');
      await tester.tap(find.text('تأكيد'));
      await tester.pumpAndSettle();

      verify(() => repository.deposit(walletId: 'wallet-1', amount: 150))
          .called(1);
      expect(find.text('تم الإيداع بنجاح.'), findsOneWidget);
      expect(find.text('15,150 DZD'), findsOneWidget);
      expect(find.text('إيداع رصيد'), findsNothing, reason: 'sheet closed');
    });

    testWidgets('rejects a non-positive amount before calling the backend',
        (WidgetTester tester) async {
      await pumpPage(tester);
      await tester.tap(find.text('إيداع'));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextFormField), '0');
      await tester.tap(find.text('تأكيد'));
      await tester.pumpAndSettle();

      expect(find.text('يجب أن يكون المبلغ أكبر من صفر.'), findsOneWidget);
      verifyNever(
        () => repository.deposit(
          walletId: any(named: 'walletId'),
          amount: any(named: 'amount'),
        ),
      );
      expect(find.text('إيداع رصيد'), findsOneWidget, reason: 'sheet stays');
    });

    testWidgets('requires an amount', (WidgetTester tester) async {
      await pumpPage(tester);
      await tester.tap(find.text('إيداع'));
      await tester.pumpAndSettle();

      await tester.tap(find.text('تأكيد'));
      await tester.pumpAndSettle();

      expect(find.text('المبلغ مطلوب.'), findsOneWidget);
    });
  });

  group('withdraw', () {
    testWidgets(
        "shows the backend's rejection message inside the sheet, where it "
        "can't be hidden behind it, and keeps the balance intact",
        (WidgetTester tester) async {
      when(
        () => repository.withdraw(
          walletId: any(named: 'walletId'),
          amount: any(named: 'amount'),
        ),
      ).thenThrow(
        const NetworkException(
          'الرصيد غير كافٍ لإتمام هذه العملية.',
          statusCode: 400,
        ),
      );

      await pumpPage(tester);
      await tester.tap(find.text('سحب'));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextFormField), '999999');
      await tester.tap(find.text('تأكيد'));
      await tester.pumpAndSettle();

      final Finder error = find.text('الرصيد غير كافٍ لإتمام هذه العملية.');
      expect(error, findsOneWidget);
      // The message must be rendered *within* the sheet, above the
      // confirm button. A `SnackBar` here would be drawn behind the
      // sheet, leaving the user staring at an apparently dead button.
      expect(find.byType(SnackBar), findsNothing);
      expect(
        tester.getCenter(error).dy,
        lessThan(tester.getCenter(find.text('تأكيد')).dy),
      );

      // The form stays up so the user can correct the amount, and the
      // balance is unchanged.
      expect(find.text('سحب رصيد'), findsOneWidget);
      expect(find.text('تأكيد'), findsOneWidget);
      expect(find.text('15,000 DZD'), findsOneWidget);
    });
  });

  group('transfer', () {
    testWidgets('collects a destination wallet id alongside the amount',
        (WidgetTester tester) async {
      when(
        () => repository.transfer(
          sourceWalletId: any(named: 'sourceWalletId'),
          destinationWalletId: any(named: 'destinationWalletId'),
          amount: any(named: 'amount'),
        ),
      ).thenAnswer((_) async => 14000);

      await pumpPage(tester);
      await tester.tap(find.text('تحويل'));
      await tester.pumpAndSettle();

      expect(find.text('تحويل رصيد'), findsOneWidget);
      expect(find.text('معرّف محفظة المستلم'), findsOneWidget);
      expect(find.byType(TextFormField), findsNWidgets(2));

      await tester.enterText(
        find.widgetWithText(TextFormField, 'معرّف محفظة المستلم'),
        'wallet-2',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'المبلغ (DZD)'),
        '1000',
      );
      await tester.tap(find.text('تأكيد'));
      await tester.pumpAndSettle();

      verify(
        () => repository.transfer(
          sourceWalletId: 'wallet-1',
          destinationWalletId: 'wallet-2',
          amount: 1000,
        ),
      ).called(1);
      expect(find.text('تم التحويل بنجاح.'), findsOneWidget);
    });

    testWidgets('requires the destination wallet id',
        (WidgetTester tester) async {
      await pumpPage(tester);
      await tester.tap(find.text('تحويل'));
      await tester.pumpAndSettle();

      await tester.enterText(
        find.widgetWithText(TextFormField, 'المبلغ (DZD)'),
        '100',
      );
      await tester.tap(find.text('تأكيد'));
      await tester.pumpAndSettle();

      expect(find.text('معرّف المحفظة مطلوب.'), findsOneWidget);
      verifyNever(
        () => repository.transfer(
          sourceWalletId: any(named: 'sourceWalletId'),
          destinationWalletId: any(named: 'destinationWalletId'),
          amount: any(named: 'amount'),
        ),
      );
    });
  });

  group('reporting back to the dashboard', () {
    /// The dashboard runs its own `WalletCubit`, so it relies on this
    /// page's pop result to know whether to re-read the balance.
    Future<Object?> pushAndLeave(
      WidgetTester tester, {
      required bool doDeposit,
    }) async {
      final WalletCubit cubit = WalletCubit(repository: repository);
      Object? popResult;

      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light,
          locale: const Locale('ar'),
          localizationsDelegates: const <LocalizationsDelegate<dynamic>>[
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: const <Locale>[Locale('ar')],
          home: Builder(
            builder: (BuildContext context) => Scaffold(
              body: TextButton(
                onPressed: () async {
                  popResult = await Navigator.of(context).push<bool>(
                    MaterialPageRoute<bool>(
                      builder: (_) => WalletDetailsPage(walletCubit: cubit),
                    ),
                  );
                },
                child: const Text('OPEN'),
              ),
            ),
          ),
        ),
      );

      await tester.tap(find.text('OPEN'));
      await tester.pumpAndSettle();

      if (doDeposit) {
        await tester.tap(find.text('إيداع'));
        await tester.pumpAndSettle();
        await tester.enterText(find.byType(TextFormField), '150');
        await tester.tap(find.text('تأكيد'));
        await tester.pumpAndSettle();
      }

      await tester.tap(find.byTooltip('رجوع'));
      await tester.pumpAndSettle();
      return popResult;
    }

    testWidgets('pops true after a successful transaction',
        (WidgetTester tester) async {
      when(
        () => repository.deposit(
          walletId: any(named: 'walletId'),
          amount: any(named: 'amount'),
        ),
      ).thenAnswer((_) async => 15150);

      expect(await pushAndLeave(tester, doDeposit: true), isTrue);
    });

    testWidgets('pops false when nothing changed', (WidgetTester tester) async {
      expect(await pushAndLeave(tester, doDeposit: false), isFalse);
    });
  });
}
