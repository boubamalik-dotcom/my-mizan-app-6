import 'package:flutter/material.dart';

import '../../../../shared/design_system/constants/app_constants.dart';
import '../../../../shared/design_system/theme/color_scheme.dart';
import '../../domain/entities/property_amenity.dart';

/// The horizontally scrollable row of premium accommodation filters
/// sitting directly under the listing screen's app bar.
///
/// Horizontal rather than wrapped: the four Arabic labels do not fit on
/// one line on a phone, and a `Wrap` would push the listings down by
/// two rows before the user has seen a single property.
class PremiumFilterBar extends StatelessWidget {
  const PremiumFilterBar({
    super.key,
    required this.selected,
    required this.onToggle,
    this.enabled = true,
  });

  final Set<PropertyAmenity> selected;
  final ValueChanged<PropertyAmenity> onToggle;

  /// False while a query is in flight, so the filters cannot be changed
  /// out from under a request that is already running.
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: MizanColors.surface,
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: SizedBox(
        height: 44,
        child: ListView.separated(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
          itemCount: PropertyAmenity.values.length,
          separatorBuilder: (_, __) => const SizedBox(width: AppSpacing.sm),
          itemBuilder: (BuildContext context, int index) {
            final PropertyAmenity amenity = PropertyAmenity.values[index];
            final bool isSelected = selected.contains(amenity);

            return Center(
              child: FilterChip(
                label: Text(amenity.label),
                avatar: Icon(
                  amenity.icon,
                  size: 17,
                  color: isSelected ? MizanColors.navy : MizanColors.gold,
                ),
                selected: isSelected,
                onSelected: enabled ? (_) => onToggle(amenity) : null,
                showCheckmark: false,
                backgroundColor: MizanColors.surface,
                selectedColor: MizanColors.gold,
                labelStyle: TextStyle(
                  color: isSelected ? MizanColors.navy : MizanColors.navy,
                  fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                  fontSize: 13,
                ),
                side: BorderSide(
                  color: isSelected
                      ? MizanColors.gold
                      : MizanColors.navy.withOpacity(0.15),
                ),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppRadius.card),
                ),
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.sm,
                  vertical: 2,
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}
