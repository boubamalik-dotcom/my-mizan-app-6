import 'package:flutter/material.dart';

/// The premium accommodation features a listing can advertise, and the
/// only things the listing screen filters on today.
///
/// Each value owns its three representations in one place so they can
/// never drift apart: the [wireValue] sent to the backend, the Arabic
/// [label] shown on its filter chip, and the [icon] beside it.
enum PropertyAmenity {
  privatePool(
    wireValue: 'private_pool',
    label: 'مسبح خاص',
    icon: Icons.pool_outlined,
  ),
  highFloor(
    wireValue: 'high_floor',
    label: 'طابق علوي',
    icon: Icons.apartment_outlined,
  ),
  kingBed(
    wireValue: 'king_bed',
    label: 'سرير ذو حجم ملكي',
    icon: Icons.king_bed_outlined,
  ),
  nonSmoking(
    wireValue: 'non_smoking',
    label: 'لغير المدخنين',
    icon: Icons.smoke_free_outlined,
  );

  const PropertyAmenity({
    required this.wireValue,
    required this.label,
    required this.icon,
  });

  /// The identifier used in API payloads and query parameters.
  final String wireValue;

  /// The Arabic name shown to the user.
  final String label;

  final IconData icon;

  /// Resolves a [wireValue] back to its amenity, or `null` for one this
  /// build does not know about.
  ///
  /// Returning `null` rather than throwing lets a listing that
  /// advertises a newer amenity still parse and display — it simply
  /// won't be filterable until the app catches up.
  static PropertyAmenity? fromWire(Object? value) {
    for (final PropertyAmenity amenity in PropertyAmenity.values) {
      if (amenity.wireValue == value) return amenity;
    }
    return null;
  }
}
