import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/mini_programs/oran_real_estate/data/datasources/property_local_datasource.dart';
import 'package:mizan_frontend/mini_programs/oran_real_estate/data/datasources/property_remote_datasource.dart';
import 'package:mizan_frontend/mini_programs/oran_real_estate/data/models/property_model.dart';
import 'package:mizan_frontend/mini_programs/oran_real_estate/data/repositories/property_repository_impl.dart';
import 'package:mizan_frontend/mini_programs/oran_real_estate/domain/entities/property.dart';
import 'package:mizan_frontend/mini_programs/oran_real_estate/domain/entities/property_amenity.dart';
import 'package:mizan_frontend/mini_programs/oran_real_estate/domain/repositories/property_repository.dart';
import 'package:mizan_frontend/shared/exceptions/network_exception.dart';
import 'package:mocktail/mocktail.dart';

class MockPropertyRemoteDataSource extends Mock
    implements PropertyRemoteDataSource {}

DioException _dioError({int? statusCode, DioExceptionType? type}) {
  final RequestOptions options = RequestOptions(path: '/properties');
  return DioException(
    requestOptions: options,
    type: type ?? DioExceptionType.badResponse,
    response: statusCode == null
        ? null
        : Response<dynamic>(requestOptions: options, statusCode: statusCode),
  );
}

Property _property({
  required String id,
  Set<PropertyAmenity> amenities = const <PropertyAmenity>{},
}) {
  return Property(
    id: id,
    title: 'شقة',
    district: 'وهران',
    price: 1000000,
    currency: 'DZD',
    bedrooms: 3,
    bathrooms: 2,
    areaSqm: 120,
    amenities: amenities,
  );
}

void main() {
  late MockPropertyRemoteDataSource remoteDataSource;
  late PropertyRepositoryImpl repository;

  setUp(() {
    remoteDataSource = MockPropertyRemoteDataSource();
    repository = PropertyRepositoryImpl(remoteDataSource: remoteDataSource);
  });

  group('live data', () {
    test('returns listings from the API and does not flag them as showcase',
        () async {
      when(
        () => remoteDataSource.fetchProperties(
          amenities: any(named: 'amenities'),
        ),
      ).thenAnswer((_) async => <Property>[_property(id: 'p1')]);

      final PropertySearchResult result = await repository.fetchProperties();

      expect(result.properties.single.id, 'p1');
      expect(result.isShowcaseData, isFalse);
    });

    test('passes the selected amenities to the API', () async {
      when(
        () => remoteDataSource.fetchProperties(
          amenities: any(named: 'amenities'),
        ),
      ).thenAnswer((_) async => <Property>[]);

      await repository.fetchProperties(
        amenities: <PropertyAmenity>{
          PropertyAmenity.privatePool,
          PropertyAmenity.highFloor,
        },
      );

      verify(
        () => remoteDataSource.fetchProperties(
          amenities: <PropertyAmenity>{
            PropertyAmenity.privatePool,
            PropertyAmenity.highFloor,
          },
        ),
      ).called(1);
    });

    test('re-applies the filter locally, so results always match the chips',
        () async {
      // Guards against an endpoint that ignores a query parameter it
      // does not understand and returns everything.
      when(
        () => remoteDataSource.fetchProperties(
          amenities: any(named: 'amenities'),
        ),
      ).thenAnswer(
        (_) async => <Property>[
          _property(id: 'has-pool', amenities: <PropertyAmenity>{
            PropertyAmenity.privatePool,
          }),
          _property(id: 'no-pool'),
        ],
      );

      final PropertySearchResult result = await repository.fetchProperties(
        amenities: <PropertyAmenity>{PropertyAmenity.privatePool},
      );

      expect(
        result.properties.map((Property p) => p.id),
        <String>['has-pool'],
      );
    });
  });

  group('showcase fallback', () {
    test('falls back to the bundled catalogue when the endpoint is absent',
        () async {
      // The property API is not deployed in mizan_backend yet.
      when(
        () => remoteDataSource.fetchProperties(
          amenities: any(named: 'amenities'),
        ),
      ).thenThrow(_dioError(statusCode: 404));

      final PropertySearchResult result = await repository.fetchProperties();

      expect(result.properties, isNotEmpty);
      expect(result.isShowcaseData, isTrue);
    });

    test('also falls back on a 501 Not Implemented', () async {
      when(
        () => remoteDataSource.fetchProperties(
          amenities: any(named: 'amenities'),
        ),
      ).thenThrow(_dioError(statusCode: 501));

      expect((await repository.fetchProperties()).isShowcaseData, isTrue);
    });

    test('filters the showcase catalogue by the selected amenities', () async {
      when(
        () => remoteDataSource.fetchProperties(
          amenities: any(named: 'amenities'),
        ),
      ).thenThrow(_dioError(statusCode: 404));

      final PropertySearchResult all = await repository.fetchProperties();
      final PropertySearchResult withPool = await repository.fetchProperties(
        amenities: <PropertyAmenity>{PropertyAmenity.privatePool},
      );

      expect(withPool.properties.length, lessThan(all.properties.length));
      expect(
        withPool.properties.every(
          (Property p) => p.amenities.contains(PropertyAmenity.privatePool),
        ),
        isTrue,
      );
    });

    test('combines amenities with AND, so each chip narrows further', () async {
      when(
        () => remoteDataSource.fetchProperties(
          amenities: any(named: 'amenities'),
        ),
      ).thenThrow(_dioError(statusCode: 404));

      final PropertySearchResult onlyPool = await repository.fetchProperties(
        amenities: <PropertyAmenity>{PropertyAmenity.privatePool},
      );
      final PropertySearchResult poolAndFloor =
          await repository.fetchProperties(
        amenities: <PropertyAmenity>{
          PropertyAmenity.privatePool,
          PropertyAmenity.highFloor,
        },
      );

      expect(
        poolAndFloor.properties.length,
        lessThan(onlyPool.properties.length),
      );
      expect(
        poolAndFloor.properties.every(
          (Property p) =>
              p.amenities.contains(PropertyAmenity.privatePool) &&
              p.amenities.contains(PropertyAmenity.highFloor),
        ),
        isTrue,
      );
    });
  });

  group('real failures are not disguised as showcase data', () {
    test('a 500 surfaces as an error', () async {
      when(
        () => remoteDataSource.fetchProperties(
          amenities: any(named: 'amenities'),
        ),
      ).thenThrow(_dioError(statusCode: 500));

      await expectLater(
        () => repository.fetchProperties(),
        throwsA(isA<NetworkException>()),
      );
    });

    test('being offline surfaces as an error rather than sample listings',
        () async {
      // Quietly showing sample listings to someone whose network is
      // down would be worse than telling them.
      when(
        () => remoteDataSource.fetchProperties(
          amenities: any(named: 'amenities'),
        ),
      ).thenThrow(_dioError(type: DioExceptionType.connectionError));

      await expectLater(
        () => repository.fetchProperties(),
        throwsA(isA<NetworkException>()),
      );
    });

    test('a 401 surfaces as an error', () async {
      when(
        () => remoteDataSource.fetchProperties(
          amenities: any(named: 'amenities'),
        ),
      ).thenThrow(_dioError(statusCode: 401));

      await expectLater(
        () => repository.fetchProperties(),
        throwsA(isA<NetworkException>()),
      );
    });
  });

  group('PropertyModel', () {
    Map<String, dynamic> payload() => <String, dynamic>{
          'id': 'p1',
          'title': 'شقة فاخرة',
          'district': 'وهران',
          'price': 42000000,
          'currency': 'DZD',
          'bedrooms': 4,
          'bathrooms': 3,
          'area_sqm': 210,
          'amenities': <String>['private_pool', 'high_floor'],
          'is_featured': true,
        };

    test('parses a listing', () {
      final Property property = PropertyModel.fromJson(payload());

      expect(property.id, 'p1');
      expect(property.title, 'شقة فاخرة');
      expect(property.price, 42000000);
      expect(property.bedrooms, 4);
      expect(property.areaSqm, 210);
      expect(property.isFeatured, isTrue);
      expect(property.amenities, <PropertyAmenity>{
        PropertyAmenity.privatePool,
        PropertyAmenity.highFloor,
      });
    });

    test('accepts numbers sent as strings', () {
      final Map<String, dynamic> json = payload()
        ..['price'] = '42000000.50'
        ..['bedrooms'] = '4';

      final Property property = PropertyModel.fromJson(json);

      expect(property.price, 42000000.5);
      expect(property.bedrooms, 4);
    });

    test('skips an unrecognised amenity instead of failing the whole load', () {
      final Map<String, dynamic> json = payload()
        ..['amenities'] = <String>['private_pool', 'helipad'];

      final Property property = PropertyModel.fromJson(json);

      expect(property.amenities, <PropertyAmenity>{
        PropertyAmenity.privatePool,
      });
    });

    test('defaults currency and featured flag when absent', () {
      final Map<String, dynamic> json = payload()
        ..remove('currency')
        ..remove('is_featured');

      final Property property = PropertyModel.fromJson(json);

      expect(property.currency, 'DZD');
      expect(property.isFeatured, isFalse);
    });

    test('rejects a payload missing a required field', () {
      final Map<String, dynamic> json = payload()..remove('title');

      expect(
        () => PropertyModel.fromJson(json),
        throwsA(isA<FormatException>()),
      );
    });
  });

  group('showcase catalogue shape', () {
    test('every filter matches some listings and excludes others', () {
      // Otherwise a chip would look broken: either a no-op or an
      // instant empty screen.
      final List<Property> catalogue =
          const PropertyLocalDataSource().showcaseCatalogue();

      for (final PropertyAmenity amenity in PropertyAmenity.values) {
        final int matching = catalogue
            .where((Property p) => p.amenities.contains(amenity))
            .length;
        expect(matching, greaterThan(0),
            reason: '${amenity.label} matches none');
        expect(
          matching,
          lessThan(catalogue.length),
          reason: '${amenity.label} matches everything',
        );
      }
    });
  });
}
