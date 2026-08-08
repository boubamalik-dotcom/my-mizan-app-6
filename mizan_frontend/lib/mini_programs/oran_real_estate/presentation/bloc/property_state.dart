import '../../domain/entities/property.dart';
import '../../domain/entities/property_amenity.dart';

/// The property listing screen's state.
///
/// A `sealed` hierarchy like `WalletState` and `ChatRoomState`, so every
/// `switch` over it is checked for exhaustiveness.
sealed class PropertyState {
  const PropertyState();

  /// The amenity chips currently selected. Carried by *every* state so
  /// the filter bar keeps rendering the user's selection while a
  /// reload is in flight or after a failure, instead of appearing to
  /// reset itself.
  Set<PropertyAmenity> get selectedAmenities;
}

/// Listings are being fetched (the initial load or a filter change).
class PropertyLoading extends PropertyState {
  const PropertyLoading({
    this.selectedAmenities = const <PropertyAmenity>{},
  });

  @override
  final Set<PropertyAmenity> selectedAmenities;
}

/// Listings loaded. [properties] may be empty when the selected filters
/// exclude everything, which the screen shows as a "no matches" state
/// rather than an error.
class PropertyLoaded extends PropertyState {
  const PropertyLoaded({
    required this.properties,
    required this.selectedAmenities,
    this.isShowcaseData = false,
  });

  final List<Property> properties;

  @override
  final Set<PropertyAmenity> selectedAmenities;

  /// True when these are the bundled illustrative listings, because the
  /// property API is not deployed yet.
  final bool isShowcaseData;

  bool get isEmpty => properties.isEmpty;
}

/// The listings could not be loaded. [message] is display-ready Arabic.
class PropertyError extends PropertyState {
  const PropertyError(this.message, {required this.selectedAmenities});

  final String message;

  @override
  final Set<PropertyAmenity> selectedAmenities;
}
