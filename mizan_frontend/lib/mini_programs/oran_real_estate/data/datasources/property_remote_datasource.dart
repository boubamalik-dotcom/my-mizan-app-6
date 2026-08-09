import 'package:dio/dio.dart';

import '../../../../shared/network/api_client.dart';
import '../../../../shared/network/endpoints.dart';
import '../../domain/entities/property.dart';
import '../../domain/entities/property_amenity.dart';
import '../models/property_model.dart';

/// Fetches property listings over HTTP.
///
/// Goes through the app-wide [ApiClient] rather than its own [Dio], so
/// every request this mini-program makes automatically carries the
/// signed-in user's JWT (`AuthInterceptor` attaches the bearer token)
/// and shares the host shell's base URL, timeouts, and forced-logout
/// handling on a 401. A mini-program never manages a session of its
/// own.
class PropertyRemoteDataSource {
  PropertyRemoteDataSource({ApiClient? apiClient})
      : _apiClient = apiClient ?? ApiClient.instance;

  final ApiClient _apiClient;

  /// `GET /properties`, narrowed to listings offering every amenity in
  /// [amenities].
  ///
  /// Amenities are sent as a repeated `amenities` query parameter
  /// (`?amenities=private_pool&amenities=high_floor`), the shape Dio
  /// produces for a list value and the one FastAPI reads back into a
  /// `list[str]` — matching how the rest of `mizan_backend` accepts
  /// query parameters.
  ///
  /// Throws the raw [DioException] on failure, for `PropertyRepository`
  /// to interpret.
  Future<List<Property>> fetchProperties({
    Set<PropertyAmenity> amenities = const <PropertyAmenity>{},
  }) async {
    final Response<dynamic> response = await _apiClient.get(
      ApiEndpoints.properties,
      queryParameters: <String, dynamic>{
        if (amenities.isNotEmpty)
          'amenities': amenities
              .map((PropertyAmenity amenity) => amenity.wireValue)
              .toList(),
      },
    );

    return _parseListings(response.data);
  }

  /// Accepts either a bare list of listings or the paginated envelope
  /// (`{"items": [...]}`) the other Mizan collection endpoints use, so
  /// whichever shape the API ships with, this keeps working.
  static List<Property> _parseListings(dynamic body) {
    final Object? listings = switch (body) {
      List<dynamic>() => body,
      Map<String, dynamic>() => body['items'] ?? body['properties'],
      _ => null,
    };

    if (listings is! List) {
      throw FormatException('Unexpected properties response: $body');
    }

    return listings
        .cast<Map<String, dynamic>>()
        .map(PropertyModel.fromJson)
        .toList(growable: false);
  }
}
