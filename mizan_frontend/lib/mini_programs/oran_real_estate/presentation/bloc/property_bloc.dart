import 'package:flutter_bloc/flutter_bloc.dart';

import '../../../../shared/exceptions/app_exception.dart';
import '../../data/repositories/property_repository_impl.dart';
import '../../domain/entities/property_amenity.dart';
import '../../domain/repositories/property_repository.dart';
import 'property_state.dart';

/// Drives the property listing screen: loads listings and re-queries
/// whenever the premium filters change.
///
/// A [Cubit] rather than a full `Bloc`, matching `WalletCubit`,
/// `ChatCubit`, and `ChatRoomCubit` — the screen's only inputs are
/// "load" and "toggle a filter", so there is no event stream worth
/// naming separately from the methods that trigger them. (This file
/// keeps its scaffolded `property_bloc.dart` name so the mini-program's
/// folder layout is untouched.)
class PropertyListingCubit extends Cubit<PropertyState> {
  PropertyListingCubit({PropertyRepository? repository})
      : _repository = repository ?? PropertyRepositoryImpl(),
        super(const PropertyLoading());

  final PropertyRepository _repository;

  /// Fetches listings for the currently selected filters.
  ///
  /// Safe to call again to retry after a [PropertyError]; the selection
  /// is preserved across the reload.
  Future<void> loadProperties() async {
    final Set<PropertyAmenity> amenities = state.selectedAmenities;
    emit(PropertyLoading(selectedAmenities: amenities));

    try {
      final PropertySearchResult result = await _repository.fetchProperties(
        amenities: amenities,
      );
      if (isClosed) return;
      emit(
        PropertyLoaded(
          properties: result.properties,
          selectedAmenities: amenities,
          isShowcaseData: result.isShowcaseData,
        ),
      );
    } on AppException catch (error) {
      if (!isClosed) {
        emit(PropertyError(error.message, selectedAmenities: amenities));
      }
    } catch (_) {
      // The screen must never be left stuck on a spinner because of an
      // unanticipated failure (e.g. a malformed payload).
      if (!isClosed) {
        emit(
          PropertyError(
            'تعذّر تحميل العقارات. يرجى المحاولة مرة أخرى.',
            selectedAmenities: amenities,
          ),
        );
      }
    }
  }

  /// Selects or clears [amenity], then reloads.
  ///
  /// Selections are cumulative and combine with AND — picking both
  /// "مسبح خاص" and "طابق علوي" asks for listings that have both — so
  /// each chip visibly narrows the results.
  Future<void> toggleAmenity(PropertyAmenity amenity) {
    final Set<PropertyAmenity> updated =
        Set<PropertyAmenity>.of(state.selectedAmenities);
    if (!updated.remove(amenity)) updated.add(amenity);

    emit(PropertyLoading(selectedAmenities: updated));
    return loadProperties();
  }

  /// Clears every filter and reloads the full catalogue.
  Future<void> clearFilters() {
    if (state.selectedAmenities.isEmpty) return Future<void>.value();
    emit(const PropertyLoading());
    return loadProperties();
  }
}
