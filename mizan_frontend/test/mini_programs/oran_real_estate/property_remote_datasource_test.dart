import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/mini_programs/oran_real_estate/data/datasources/property_remote_datasource.dart';
import 'package:mizan_frontend/mini_programs/oran_real_estate/domain/entities/property.dart';
import 'package:mizan_frontend/mini_programs/oran_real_estate/domain/entities/property_amenity.dart';
import 'package:mizan_frontend/shared/network/api_client.dart';
import 'package:mocktail/mocktail.dart';

class MockApiClient extends Mock implements ApiClient {}

Response<dynamic> _response(dynamic data) {
  return Response<dynamic>(
    requestOptions: RequestOptions(path: '/properties'),
    statusCode: 200,
    data: data,
  );
}

Map<String, dynamic> _listing(String id) => <String, dynamic>{
      'id': id,
      'title': 'شقة فاخرة',
      'district': 'وهران',
      'price': 42000000,
      'currency': 'DZD',
      'bedrooms': 4,
      'bathrooms': 3,
      'area_sqm': 210,
      'amenities': <String>['private_pool'],
    };

void main() {
  late MockApiClient apiClient;
  late PropertyRemoteDataSource dataSource;

  setUp(() {
    apiClient = MockApiClient();
    dataSource = PropertyRemoteDataSource(apiClient: apiClient);
  });

  test('goes through the shared ApiClient, so requests inherit the JWT',
      () async {
    // The whole point of requirement: a mini-program never manages a
    // session of its own. Using ApiClient means AuthInterceptor attaches
    // the bearer token and handles a 401 the same way it does for the
    // wallet and chat features.
    when(() => apiClient.get(any(),
        queryParameters: any(named: 'queryParameters'))).thenAnswer(
      (_) async => _response(<Map<String, dynamic>>[_listing('p1')]),
    );

    final List<Property> listings = await dataSource.fetchProperties();

    expect(listings.single.id, 'p1');
    verify(
      () => apiClient.get('/properties', queryParameters: <String, dynamic>{}),
    ).called(1);
  });

  test('sends the selected amenities as repeated query parameters', () async {
    when(() => apiClient.get(any(),
            queryParameters: any(named: 'queryParameters')))
        .thenAnswer((_) async => _response(<Map<String, dynamic>>[]));

    await dataSource.fetchProperties(
      amenities: <PropertyAmenity>{
        PropertyAmenity.privatePool,
        PropertyAmenity.nonSmoking,
      },
    );

    final Map<String, dynamic> sent = verify(
      () => apiClient.get(
        '/properties',
        queryParameters: captureAny(named: 'queryParameters'),
      ),
    ).captured.single as Map<String, dynamic>;

    expect(sent['amenities'], <String>['private_pool', 'non_smoking']);
  });

  test('omits the parameter entirely when nothing is selected', () async {
    when(() => apiClient.get(any(),
            queryParameters: any(named: 'queryParameters')))
        .thenAnswer((_) async => _response(<Map<String, dynamic>>[]));

    await dataSource.fetchProperties();

    final Map<String, dynamic> sent = verify(
      () => apiClient.get(
        '/properties',
        queryParameters: captureAny(named: 'queryParameters'),
      ),
    ).captured.single as Map<String, dynamic>;

    expect(sent.containsKey('amenities'), isFalse);
  });

  group('response shapes', () {
    test('accepts a bare list', () async {
      when(() => apiClient.get(any(),
          queryParameters: any(named: 'queryParameters'))).thenAnswer(
        (_) async => _response(<Map<String, dynamic>>[_listing('p1')]),
      );

      expect((await dataSource.fetchProperties()).single.id, 'p1');
    });

    test('accepts the paginated `items` envelope', () async {
      when(() => apiClient.get(any(),
          queryParameters: any(named: 'queryParameters'))).thenAnswer(
        (_) async => _response(<String, dynamic>{
          'items': <Map<String, dynamic>>[_listing('p2')],
        }),
      );

      expect((await dataSource.fetchProperties()).single.id, 'p2');
    });

    test('rejects a shape it cannot read rather than returning nothing',
        () async {
      when(() => apiClient.get(any(),
              queryParameters: any(named: 'queryParameters')))
          .thenAnswer((_) async => _response('not a list'));

      await expectLater(
        () => dataSource.fetchProperties(),
        throwsA(isA<FormatException>()),
      );
    });
  });
}
