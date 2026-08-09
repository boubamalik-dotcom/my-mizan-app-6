import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/mini_programs/oran_real_estate/domain/entities/property.dart';
import 'package:mizan_frontend/mini_programs/oran_real_estate/domain/entities/property_amenity.dart';
import 'package:mizan_frontend/mini_programs/oran_real_estate/domain/repositories/property_repository.dart';
import 'package:mizan_frontend/mini_programs/oran_real_estate/presentation/bloc/property_bloc.dart';
import 'package:mizan_frontend/mini_programs/oran_real_estate/presentation/bloc/property_state.dart';
import 'package:mizan_frontend/shared/exceptions/network_exception.dart';
import 'package:mocktail/mocktail.dart';

class MockPropertyRepository extends Mock implements PropertyRepository {}

Property _property(String id) => Property(
      id: id,
      title: 'شقة',
      district: 'وهران',
      price: 1000000,
      currency: 'DZD',
      bedrooms: 3,
      bathrooms: 2,
      areaSqm: 120,
      amenities: const <PropertyAmenity>{},
    );

void main() {
  late MockPropertyRepository repository;
  late PropertyListingCubit cubit;

  setUp(() {
    repository = MockPropertyRepository();
    when(() => repository.fetchProperties(amenities: any(named: 'amenities')))
        .thenAnswer(
      (_) async => PropertySearchResult(
        properties: <Property>[_property('p1')],
        isShowcaseData: false,
      ),
    );
    cubit = PropertyListingCubit(repository: repository);
  });

  tearDown(() async => cubit.close());

  test('starts loading with no filters selected', () {
    expect(cubit.state, isA<PropertyLoading>());
    expect(cubit.state.selectedAmenities, isEmpty);
  });

  test('loadProperties emits the listings', () async {
    await cubit.loadProperties();

    final PropertyLoaded state = cubit.state as PropertyLoaded;
    expect(state.properties.single.id, 'p1');
    expect(state.isShowcaseData, isFalse);
  });

  test('carries the showcase flag through to the state', () async {
    when(() => repository.fetchProperties(amenities: any(named: 'amenities')))
        .thenAnswer(
      (_) async => PropertySearchResult(
        properties: <Property>[_property('p1')],
        isShowcaseData: true,
      ),
    );

    await cubit.loadProperties();

    expect((cubit.state as PropertyLoaded).isShowcaseData, isTrue);
  });

  test('an empty result is a loaded state, not an error', () async {
    when(() => repository.fetchProperties(amenities: any(named: 'amenities')))
        .thenAnswer(
      (_) async => const PropertySearchResult(
        properties: <Property>[],
        isShowcaseData: false,
      ),
    );

    await cubit.loadProperties();

    expect(cubit.state, isA<PropertyLoaded>());
    expect((cubit.state as PropertyLoaded).isEmpty, isTrue);
  });

  group('filters', () {
    test('toggling an amenity selects it and re-queries', () async {
      await cubit.loadProperties();

      await cubit.toggleAmenity(PropertyAmenity.privatePool);

      expect(
        cubit.state.selectedAmenities,
        <PropertyAmenity>{PropertyAmenity.privatePool},
      );
      verify(
        () => repository.fetchProperties(
          amenities: <PropertyAmenity>{PropertyAmenity.privatePool},
        ),
      ).called(1);
    });

    test('toggling the same amenity again clears it', () async {
      await cubit.toggleAmenity(PropertyAmenity.highFloor);
      await cubit.toggleAmenity(PropertyAmenity.highFloor);

      expect(cubit.state.selectedAmenities, isEmpty);
    });

    test('selections accumulate, combining with AND', () async {
      await cubit.toggleAmenity(PropertyAmenity.privatePool);
      await cubit.toggleAmenity(PropertyAmenity.kingBed);

      expect(cubit.state.selectedAmenities, <PropertyAmenity>{
        PropertyAmenity.privatePool,
        PropertyAmenity.kingBed,
      });
      verify(
        () => repository.fetchProperties(
          amenities: <PropertyAmenity>{
            PropertyAmenity.privatePool,
            PropertyAmenity.kingBed,
          },
        ),
      ).called(1);
    });

    test('clearFilters drops every selection and reloads', () async {
      await cubit.toggleAmenity(PropertyAmenity.privatePool);
      await cubit.toggleAmenity(PropertyAmenity.nonSmoking);

      await cubit.clearFilters();

      expect(cubit.state.selectedAmenities, isEmpty);
      verify(() => repository.fetchProperties(amenities: <PropertyAmenity>{}))
          .called(greaterThanOrEqualTo(1));
    });

    test('clearFilters does nothing when nothing is selected', () async {
      await cubit.loadProperties();
      clearInteractions(repository);

      await cubit.clearFilters();

      verifyNever(
        () => repository.fetchProperties(amenities: any(named: 'amenities')),
      );
    });

    test(
        'the selection survives a failed load, so the chips do not appear '
        'to reset themselves', () async {
      await cubit.toggleAmenity(PropertyAmenity.privatePool);

      when(() => repository.fetchProperties(amenities: any(named: 'amenities')))
          .thenThrow(const NetworkException('تعذّر الاتصال بالخادم.'));
      await cubit.loadProperties();

      expect(cubit.state, isA<PropertyError>());
      expect(
        cubit.state.selectedAmenities,
        <PropertyAmenity>{PropertyAmenity.privatePool},
      );
    });

    test('a retry after a failure re-sends the same filters', () async {
      await cubit.toggleAmenity(PropertyAmenity.kingBed);
      when(() => repository.fetchProperties(amenities: any(named: 'amenities')))
          .thenThrow(const NetworkException('تعذّر الاتصال بالخادم.'));
      await cubit.loadProperties();
      clearInteractions(repository);

      when(() => repository.fetchProperties(amenities: any(named: 'amenities')))
          .thenAnswer(
        (_) async => PropertySearchResult(
          properties: <Property>[_property('p1')],
          isShowcaseData: false,
        ),
      );
      await cubit.loadProperties();

      expect(cubit.state, isA<PropertyLoaded>());
      verify(
        () => repository.fetchProperties(
          amenities: <PropertyAmenity>{PropertyAmenity.kingBed},
        ),
      ).called(1);
    });
  });

  group('failures', () {
    test('surfaces an AppException message verbatim', () async {
      when(() => repository.fetchProperties(amenities: any(named: 'amenities')))
          .thenThrow(const NetworkException('تعذّر الاتصال بالخادم.'));

      await cubit.loadProperties();

      expect((cubit.state as PropertyError).message, 'تعذّر الاتصال بالخادم.');
    });

    test('falls back to a generic Arabic message for anything else', () async {
      when(() => repository.fetchProperties(amenities: any(named: 'amenities')))
          .thenThrow(StateError('boom'));

      await cubit.loadProperties();

      expect(
        (cubit.state as PropertyError).message,
        contains('تعذّر تحميل العقارات'),
      );
    });
  });
}
