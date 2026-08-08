import '../../domain/entities/property.dart';
import '../../domain/entities/property_amenity.dart';

/// Builds [Property] objects from API payloads.
///
/// The property API does not exist in `mizan_backend` yet, so this
/// mapping is the contract the frontend *expects* rather than one
/// verified against a live endpoint (unlike, say, `WalletModel`). It is
/// deliberately tolerant — numbers may arrive as JSON numbers or as
/// strings, unknown amenities are skipped rather than fatal — so the
/// first real payload is unlikely to break it outright. Re-check it
/// against the real schema when the endpoint lands.
class PropertyModel {
  const PropertyModel._();

  static Property fromJson(Map<String, dynamic> json) {
    return Property(
      id: _requireString(json, 'id'),
      title: _requireString(json, 'title'),
      district: _requireString(json, 'district'),
      price: _requireNumber(json, 'price'),
      currency: json['currency'] as String? ?? 'DZD',
      bedrooms: _requireNumber(json, 'bedrooms').toInt(),
      bathrooms: _requireNumber(json, 'bathrooms').toInt(),
      areaSqm: _requireNumber(json, 'area_sqm').toInt(),
      amenities: _amenities(json['amenities']),
      isFeatured: json['is_featured'] as bool? ?? false,
    );
  }

  /// Skips amenities this build does not recognise instead of failing,
  /// so a backend that adds one does not break older clients — the
  /// listing simply isn't filterable on it yet.
  static Set<PropertyAmenity> _amenities(Object? value) {
    if (value is! List) return <PropertyAmenity>{};
    return value
        .map(PropertyAmenity.fromWire)
        .whereType<PropertyAmenity>()
        .toSet();
  }

  static String _requireString(Map<String, dynamic> json, String field) {
    final Object? value = json[field];
    if (value is String) return value;
    throw FormatException('Expected a string `$field`, got: $value');
  }

  static double _requireNumber(Map<String, dynamic> json, String field) {
    final Object? value = json[field];
    if (value is num) return value.toDouble();
    if (value is String) {
      final double? parsed = double.tryParse(value);
      if (parsed != null) return parsed;
    }
    throw FormatException('Expected a numeric `$field`, got: $value');
  }
}
