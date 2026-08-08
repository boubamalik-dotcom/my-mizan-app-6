import 'package:dio/dio.dart';

import '../../../../shared/exceptions/network_exception.dart';
import '../../domain/entities/property.dart';
import '../../domain/entities/property_amenity.dart';
import '../../domain/repositories/property_repository.dart';
import '../datasources/property_local_datasource.dart';
import '../datasources/property_remote_datasource.dart';

/// Serves listings from the API, falling back to the bundled showcase
/// catalogue only while the API does not exist.
class PropertyRepositoryImpl implements PropertyRepository {
  PropertyRepositoryImpl({
    PropertyRemoteDataSource? remoteDataSource,
    PropertyLocalDataSource localDataSource = const PropertyLocalDataSource(),
  })  : _remoteDataSource = remoteDataSource ?? PropertyRemoteDataSource(),
        _localDataSource = localDataSource;

  final PropertyRemoteDataSource _remoteDataSource;
  final PropertyLocalDataSource _localDataSource;

  @override
  Future<PropertySearchResult> fetchProperties({
    Set<PropertyAmenity> amenities = const <PropertyAmenity>{},
  }) async {
    try {
      final List<Property> listings = await _remoteDataSource.fetchProperties(
        amenities: amenities,
      );
      return PropertySearchResult(
        properties: _applyFilter(listings, amenities),
        isShowcaseData: false,
      );
    } on DioException catch (error) {
      if (_isEndpointMissing(error)) {
        return PropertySearchResult(
          properties: _applyFilter(
            _localDataSource.showcaseCatalogue(),
            amenities,
          ),
          isShowcaseData: true,
        );
      }
      throw NetworkException.fromDioException(error);
    }
  }

  /// Whether the failure means "this API isn't deployed yet" as opposed
  /// to "the request failed".
  ///
  /// Narrow on purpose: only a **404** (no such route) or a **501**
  /// (explicitly not implemented) fall back to showcase data. An
  /// offline device, a timeout, a 401, or a 500 must surface as a real
  /// error — quietly showing sample listings to someone whose network
  /// is down would be worse than telling them.
  bool _isEndpointMissing(DioException error) {
    final int? status = error.response?.statusCode;
    return status == 404 || status == 501;
  }

  /// Applies the amenity filter locally as a final pass, whichever
  /// source the listings came from.
  ///
  /// The query parameters already ask the API to filter; re-applying
  /// here means the results on screen always match the selected chips
  /// even if the endpoint ignores a parameter it does not understand.
  List<Property> _applyFilter(
    List<Property> listings,
    Set<PropertyAmenity> amenities,
  ) {
    if (amenities.isEmpty) return listings;
    return listings
        .where((Property property) => property.matchesAll(amenities))
        .toList(growable: false);
  }
}
