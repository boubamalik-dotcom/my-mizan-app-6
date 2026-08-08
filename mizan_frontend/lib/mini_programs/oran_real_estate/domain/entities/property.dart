import 'property_amenity.dart';

/// A property listing, as the Oran Real Estate mini-program's UI needs
/// it.
///
/// Deliberately free of any JSON or transport concern — `PropertyModel`
/// in the data layer is what knows how to build one of these from an
/// API payload.
class Property {
  const Property({
    required this.id,
    required this.title,
    required this.district,
    required this.price,
    required this.currency,
    required this.bedrooms,
    required this.bathrooms,
    required this.areaSqm,
    required this.amenities,
    this.isFeatured = false,
  });

  final String id;

  /// Arabic headline, e.g. "شقة فاخرة بإطلالة بحرية".
  final String title;

  /// The neighbourhood or district, shown under the title.
  final String district;

  final double price;
  final String currency;

  final int bedrooms;
  final int bathrooms;

  /// Floor area in square metres.
  final int areaSqm;

  final Set<PropertyAmenity> amenities;

  /// Whether to give the listing the gold "مميّز" ribbon.
  final bool isFeatured;

  /// Whether this listing offers every amenity in [required].
  ///
  /// An empty [required] matches everything, which is what makes "no
  /// chips selected" mean "show all" without a special case at the call
  /// site.
  bool matchesAll(Set<PropertyAmenity> required) {
    return required.every(amenities.contains);
  }

  @override
  bool operator ==(Object other) => other is Property && other.id == id;

  @override
  int get hashCode => id.hashCode;

  @override
  String toString() => 'Property($id, $title)';
}
