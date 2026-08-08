import '../entities/property.dart';
import '../entities/property_amenity.dart';

/// What a property search returned, and where it came from.
class PropertySearchResult {
  const PropertySearchResult({
    required this.properties,
    required this.isShowcaseData,
  });

  final List<Property> properties;

  /// True when these are the bundled illustrative listings rather than
  /// live inventory, because the property API is not deployed yet. The
  /// screen surfaces this to the user rather than passing sample data
  /// off as real.
  final bool isShowcaseData;
}

/// The Oran Real Estate mini-program's data contract.
///
/// Declared in the domain layer so the presentation layer depends on
/// this rather than on the HTTP implementation, which is what lets the
/// listing cubit be tested without a network at all.
abstract class PropertyRepository {
  /// Listings offering every amenity in [amenities]; all listings when
  /// it is empty.
  Future<PropertySearchResult> fetchProperties({
    Set<PropertyAmenity> amenities,
  });
}
