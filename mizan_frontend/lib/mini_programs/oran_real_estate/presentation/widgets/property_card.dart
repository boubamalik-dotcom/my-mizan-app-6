import 'package:flutter/material.dart';
import 'package:intl/intl.dart' show NumberFormat;

import '../../../../shared/design_system/constants/app_constants.dart';
import '../../../../shared/design_system/theme/color_scheme.dart';
import '../../domain/entities/property.dart';
import '../../domain/entities/property_amenity.dart';

/// One listing: a crisp white card with the Mizan 16px radius, a navy
/// header band, and the price in gold.
///
/// The header is a navy gradient rather than a photograph — the
/// mini-program has no image pipeline or CDN yet, and a broken image
/// placeholder would undercut exactly the mid-to-high-end feel this
/// screen is meant to convey.
class PropertyCard extends StatelessWidget {
  const PropertyCard({super.key, required this.property, this.onTap});

  final Property property;
  final VoidCallback? onTap;

  static final NumberFormat _priceFormat = NumberFormat('#,##0');

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: AppSpacing.md),
      decoration: BoxDecoration(
        color: MizanColors.surface,
        borderRadius: AppRadius.cardRadius,
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: MizanColors.navy.withOpacity(0.07),
            blurRadius: 16,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              _CardHeader(property: property),
              Padding(
                padding: const EdgeInsets.all(AppSpacing.md),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      property.title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 2),
                    Row(
                      children: <Widget>[
                        const Icon(
                          Icons.location_on_outlined,
                          size: 14,
                          color: MizanColors.textSecondary,
                        ),
                        const SizedBox(width: 4),
                        Expanded(
                          child: Text(
                            property.district,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    _SpecsRow(property: property),
                    if (property.amenities.isNotEmpty) ...<Widget>[
                      const SizedBox(height: AppSpacing.sm),
                      _AmenityTags(amenities: property.amenities),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Navy band carrying the price and, when applicable, the gold
/// "featured" ribbon.
class _CardHeader extends StatelessWidget {
  const _CardHeader({required this.property});

  final Property property;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 92,
      width: double.infinity,
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topRight,
          end: Alignment.bottomLeft,
          colors: <Color>[MizanColors.navy, MizanColors.navyDark],
        ),
      ),
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(
                Icons.apartment_rounded,
                color: Colors.white24,
                size: 26,
              ),
              const Spacer(),
              if (property.isFeatured) const _FeaturedRibbon(),
            ],
          ),
          Text(
            '${PropertyCard._priceFormat.format(property.price)} '
            '${property.currency}',
            textDirection: TextDirection.ltr,
            style: const TextStyle(
              color: MizanColors.gold,
              fontSize: 20,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }
}

class _FeaturedRibbon extends StatelessWidget {
  const _FeaturedRibbon();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding:
          const EdgeInsets.symmetric(horizontal: AppSpacing.sm, vertical: 3),
      decoration: BoxDecoration(
        color: MizanColors.gold,
        borderRadius: BorderRadius.circular(AppRadius.card / 2),
      ),
      child: const Text(
        'مميّز',
        style: TextStyle(
          color: MizanColors.navy,
          fontSize: 11,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

/// Bedrooms / bathrooms / area, the three figures a buyer scans first.
class _SpecsRow extends StatelessWidget {
  const _SpecsRow({required this.property});

  final Property property;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        _Spec(icon: Icons.bed_outlined, value: '${property.bedrooms} غرف'),
        const SizedBox(width: AppSpacing.md),
        _Spec(
          icon: Icons.bathtub_outlined,
          value: '${property.bathrooms} حمّام',
        ),
        const SizedBox(width: AppSpacing.md),
        _Spec(
          icon: Icons.straighten_outlined,
          value: '${property.areaSqm} م²',
        ),
      ],
    );
  }
}

class _Spec extends StatelessWidget {
  const _Spec({required this.icon, required this.value});

  final IconData icon;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Icon(icon, size: 15, color: MizanColors.gold),
        const SizedBox(width: 4),
        Text(
          value,
          style: const TextStyle(
            color: MizanColors.navy,
            fontSize: 12,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }
}

/// The premium features this listing offers, in the same wording as the
/// filter chips above so a match is obvious at a glance.
class _AmenityTags extends StatelessWidget {
  const _AmenityTags({required this.amenities});

  final Set<PropertyAmenity> amenities;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: AppSpacing.xs,
      runSpacing: AppSpacing.xs,
      children: amenities.map((PropertyAmenity amenity) {
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          decoration: BoxDecoration(
            color: MizanColors.gold.withOpacity(0.12),
            borderRadius: BorderRadius.circular(AppRadius.card / 2),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(amenity.icon, size: 13, color: MizanColors.gold),
              const SizedBox(width: 4),
              Text(
                amenity.label,
                style: const TextStyle(
                  color: MizanColors.navy,
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        );
      }).toList(),
    );
  }
}
