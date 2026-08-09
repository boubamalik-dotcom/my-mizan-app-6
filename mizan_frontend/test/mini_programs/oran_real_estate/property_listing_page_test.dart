import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/mini_programs/oran_real_estate/domain/entities/property.dart';
import 'package:mizan_frontend/mini_programs/oran_real_estate/domain/entities/property_amenity.dart';
import 'package:mizan_frontend/mini_programs/oran_real_estate/domain/repositories/property_repository.dart';
import 'package:mizan_frontend/mini_programs/oran_real_estate/presentation/bloc/property_bloc.dart';
import 'package:mizan_frontend/mini_programs/oran_real_estate/presentation/pages/property_listing_page.dart';
import 'package:mizan_frontend/mini_programs/oran_real_estate/presentation/widgets/property_card.dart';
import 'package:mizan_frontend/shared/design_system/theme/app_theme.dart';
import 'package:mizan_frontend/shared/design_system/theme/color_scheme.dart';
import 'package:mizan_frontend/shared/exceptions/network_exception.dart';
import 'package:mocktail/mocktail.dart';

class MockPropertyRepository extends Mock implements PropertyRepository {}

Property _property({
  required String id,
  String title = 'شقة فاخرة',
  Set<PropertyAmenity> amenities = const <PropertyAmenity>{},
  bool isFeatured = false,
}) {
  return Property(
    id: id,
    title: title,
    district: 'وهران',
    price: 42000000,
    currency: 'DZD',
    bedrooms: 4,
    bathrooms: 3,
    areaSqm: 210,
    amenities: amenities,
    isFeatured: isFeatured,
  );
}

void main() {
  late MockPropertyRepository repository;

  /// Answers each query by filtering [catalogue] the way the real
  /// repository does, so the page's filter interactions can be exercised
  /// end to end.
  void stubCatalogue(List<Property> catalogue, {bool isShowcase = false}) {
    when(() => repository.fetchProperties(amenities: any(named: 'amenities')))
        .thenAnswer((Invocation invocation) async {
      final Set<PropertyAmenity> amenities =
          invocation.namedArguments[#amenities] as Set<PropertyAmenity>? ??
              <PropertyAmenity>{};
      return PropertySearchResult(
        properties:
            catalogue.where((Property p) => p.matchesAll(amenities)).toList(),
        isShowcaseData: isShowcase,
      );
    });
  }

  setUp(() {
    repository = MockPropertyRepository();
    stubCatalogue(<Property>[_property(id: 'p1')]);
  });

  Future<void> pumpPage(WidgetTester tester) async {
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
        home: PropertyListingPage(
          listingCubit: PropertyListingCubit(repository: repository),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  group('layout', () {
    testWidgets('shows the Arabic title and all four premium filter chips',
        (WidgetTester tester) async {
      await pumpPage(tester);

      expect(find.text('عقارات وهران'), findsOneWidget);
      expect(find.widgetWithText(FilterChip, 'مسبح خاص'), findsOneWidget);
      expect(find.widgetWithText(FilterChip, 'طابق علوي'), findsOneWidget);
      expect(
        find.widgetWithText(FilterChip, 'سرير ذو حجم ملكي'),
        findsOneWidget,
      );
      expect(find.widgetWithText(FilterChip, 'لغير المدخنين'), findsOneWidget);
    });

    testWidgets('the filter row scrolls horizontally',
        (WidgetTester tester) async {
      // Four Arabic labels do not fit on a phone's width; wrapping them
      // would push the listings two rows down.
      await pumpPage(tester);

      final ScrollableState scrollable = tester.state<ScrollableState>(
        find
            .descendant(
              of: find.byType(ListView),
              matching: find.byType(Scrollable),
            )
            .first,
      );
      expect(scrollable.position.axis, Axis.horizontal);
    });

    testWidgets('renders right-to-left', (WidgetTester tester) async {
      await pumpPage(tester);

      expect(
        Directionality.of(tester.element(find.text('عقارات وهران'))),
        TextDirection.rtl,
      );
    });

    testWidgets('uses the Mizan navy app bar', (WidgetTester tester) async {
      await pumpPage(tester);

      final AppBar appBar = tester.widget<AppBar>(find.byType(AppBar));
      final Color? resolved = appBar.backgroundColor ??
          Theme.of(tester.element(find.byType(AppBar)))
              .appBarTheme
              .backgroundColor;
      expect(resolved, MizanColors.navy);
    });

    testWidgets('property cards use the 16px Mizan radius',
        (WidgetTester tester) async {
      await pumpPage(tester);

      final Container card = tester.widget<Container>(
        find
            .descendant(
              of: find.byType(PropertyCard),
              matching: find.byType(Container),
            )
            .first,
      );
      final BoxDecoration decoration = card.decoration! as BoxDecoration;
      expect(decoration.color, MizanColors.surface);
      expect(decoration.borderRadius, BorderRadius.circular(16));
    });

    testWidgets('shows a spinner while the query is in flight',
        (WidgetTester tester) async {
      // Gated on a Completer: a mock that resolves on a microtask would
      // already be loaded by the first pump, and the loading state would
      // never be observable.
      final Completer<PropertySearchResult> pending =
          Completer<PropertySearchResult>();
      when(() => repository.fetchProperties(amenities: any(named: 'amenities')))
          .thenAnswer((_) => pending.future);

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
          home: PropertyListingPage(
            listingCubit: PropertyListingCubit(repository: repository),
          ),
        ),
      );
      await tester.pump();

      expect(find.byType(CircularProgressIndicator), findsOneWidget);

      pending.complete(
        PropertySearchResult(
          properties: <Property>[_property(id: 'p1')],
          isShowcaseData: false,
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(CircularProgressIndicator), findsNothing);
      expect(find.byType(PropertyCard), findsOneWidget);
    });
  });

  group('listings', () {
    testWidgets('renders a card per listing with its price and amenities',
        (WidgetTester tester) async {
      stubCatalogue(<Property>[
        _property(
          id: 'p1',
          title: 'فيلا بمسبح',
          isFeatured: true,
          amenities: <PropertyAmenity>{PropertyAmenity.privatePool},
        ),
        _property(id: 'p2', title: 'شقة بإطلالة'),
      ]);

      await pumpPage(tester);

      expect(find.byType(PropertyCard), findsNWidgets(2));
      expect(find.text('فيلا بمسبح'), findsOneWidget);
      expect(find.text('42,000,000 DZD'), findsNWidgets(2));
      expect(find.text('مميّز'), findsOneWidget);
    });

    testWidgets('shows the showcase notice only for illustrative listings',
        (WidgetTester tester) async {
      stubCatalogue(<Property>[_property(id: 'p1')], isShowcase: true);

      await pumpPage(tester);

      expect(find.textContaining('عقارات تجريبية'), findsOneWidget);
    });

    testWidgets('does not claim showcase data when the listings are live',
        (WidgetTester tester) async {
      await pumpPage(tester);

      expect(find.textContaining('عقارات تجريبية'), findsNothing);
    });
  });

  group('filtering', () {
    testWidgets('tapping a chip narrows the listings to matches',
        (WidgetTester tester) async {
      stubCatalogue(<Property>[
        _property(
          id: 'pool',
          title: 'فيلا بمسبح',
          amenities: <PropertyAmenity>{PropertyAmenity.privatePool},
        ),
        _property(id: 'plain', title: 'شقة عادية'),
      ]);
      await pumpPage(tester);
      expect(find.byType(PropertyCard), findsNWidgets(2));

      await tester.tap(find.widgetWithText(FilterChip, 'مسبح خاص'));
      await tester.pumpAndSettle();

      expect(find.byType(PropertyCard), findsOneWidget);
      expect(find.text('فيلا بمسبح'), findsOneWidget);
      expect(find.text('شقة عادية'), findsNothing);
      verify(
        () => repository.fetchProperties(
          amenities: <PropertyAmenity>{PropertyAmenity.privatePool},
        ),
      ).called(1);
    });

    testWidgets('the match count tracks the filters and survives scrolling',
        (WidgetTester tester) async {
      // The count is the feedback that makes a filter's effect legible,
      // so it is pinned above the list rather than scrolling away with
      // it.
      stubCatalogue(<Property>[
        for (int i = 0; i < 8; i++)
          _property(
            id: 'p$i',
            amenities: i.isEven
                ? <PropertyAmenity>{PropertyAmenity.privatePool}
                : const <PropertyAmenity>{},
          ),
      ]);
      await pumpPage(tester);

      expect(find.text('العقارات المتاحة'), findsOneWidget);
      expect(find.text('8'), findsOneWidget);

      await tester.drag(find.byType(PropertyCard).first, const Offset(0, -400));
      await tester.pumpAndSettle();
      expect(find.text('8'), findsOneWidget, reason: 'still pinned');

      await tester.tap(find.widgetWithText(FilterChip, 'مسبح خاص'));
      await tester.pumpAndSettle();

      expect(find.text('4'), findsOneWidget);
    });

    testWidgets('the chip shows as selected after tapping',
        (WidgetTester tester) async {
      await pumpPage(tester);

      await tester.tap(find.widgetWithText(FilterChip, 'طابق علوي'));
      await tester.pumpAndSettle();

      final FilterChip chip = tester.widget<FilterChip>(
        find.widgetWithText(FilterChip, 'طابق علوي'),
      );
      expect(chip.selected, isTrue);
      expect(chip.selectedColor, MizanColors.gold);
    });

    testWidgets('tapping the chip again restores the full list',
        (WidgetTester tester) async {
      stubCatalogue(<Property>[
        _property(
          id: 'pool',
          amenities: <PropertyAmenity>{PropertyAmenity.privatePool},
        ),
        _property(id: 'plain'),
      ]);
      await pumpPage(tester);

      await tester.tap(find.widgetWithText(FilterChip, 'مسبح خاص'));
      await tester.pumpAndSettle();
      expect(find.byType(PropertyCard), findsOneWidget);

      await tester.tap(find.widgetWithText(FilterChip, 'مسبح خاص'));
      await tester.pumpAndSettle();
      expect(find.byType(PropertyCard), findsNWidgets(2));
    });

    testWidgets(
        'an over-narrow filter shows the no-matches state with a way '
        'back', (WidgetTester tester) async {
      stubCatalogue(<Property>[_property(id: 'plain')]);
      await pumpPage(tester);

      await tester.tap(find.widgetWithText(FilterChip, 'مسبح خاص'));
      await tester.pumpAndSettle();

      expect(find.text('لا توجد عقارات مطابقة'), findsOneWidget);
      expect(find.byType(PropertyCard), findsNothing);

      await tester.tap(find.text('إزالة عوامل التصفية'));
      await tester.pumpAndSettle();

      expect(find.byType(PropertyCard), findsOneWidget);
    });
  });

  group('failure', () {
    testWidgets('shows the error with a working retry',
        (WidgetTester tester) async {
      when(() => repository.fetchProperties(amenities: any(named: 'amenities')))
          .thenThrow(const NetworkException('تعذّر الاتصال بالخادم.'));

      await pumpPage(tester);

      expect(find.text('تعذّر الاتصال بالخادم.'), findsOneWidget);
      expect(find.text('إعادة المحاولة'), findsOneWidget);
      // The filter bar stays put so the selection is not lost.
      expect(find.widgetWithText(FilterChip, 'مسبح خاص'), findsOneWidget);

      stubCatalogue(<Property>[_property(id: 'p1')]);
      await tester.tap(find.text('إعادة المحاولة'));
      await tester.pumpAndSettle();

      expect(find.byType(PropertyCard), findsOneWidget);
    });
  });
}
