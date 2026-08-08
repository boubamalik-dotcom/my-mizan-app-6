import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../../../shared/design_system/constants/app_constants.dart';
import '../../../../shared/design_system/theme/color_scheme.dart';
import '../../domain/entities/property.dart';
import '../../domain/entities/property_amenity.dart';
import '../bloc/property_bloc.dart';
import '../bloc/property_state.dart';
import '../widgets/premium_filter_bar.dart';
import '../widgets/property_card.dart';

/// "عقارات وهران" — the Oran Real Estate mini-program's main screen:
/// premium accommodation filters over a list of listings.
///
/// Reached two ways, both landing here so the mini-program has a single
/// entry point: the dashboard's Oran card pushes `CoreRoutes.realEstate`
/// directly, and `OranRealEstateMiniProgram.buildRootWidget` returns
/// this page for anything going through the host shell's mini-program
/// loader.
class PropertyListingPage extends StatelessWidget {
  const PropertyListingPage({super.key, PropertyListingCubit? listingCubit})
      : _cubitOverride = listingCubit;

  /// Injectable for tests, which must not hit the network. In
  /// production a fresh cubit is created and immediately told to
  /// [PropertyListingCubit.loadProperties].
  final PropertyListingCubit? _cubitOverride;

  @override
  Widget build(BuildContext context) {
    return BlocProvider<PropertyListingCubit>(
      create: (_) =>
          (_cubitOverride ?? PropertyListingCubit())..loadProperties(),
      child: Builder(
        builder: (BuildContext context) => Scaffold(
          backgroundColor: MizanColors.background,
          appBar: AppBar(
            title: const Text('عقارات وهران'),
            leading: IconButton(
              // Points forward in reading order, which under the app's
              // RTL layout is the correct "back" direction.
              icon: const Icon(Icons.arrow_forward_rounded),
              tooltip: 'رجوع',
              onPressed: () => Navigator.of(context).pop(),
            ),
          ),
          body: Column(
            children: <Widget>[
              BlocBuilder<PropertyListingCubit, PropertyState>(
                // Scoped to the filter bar: it only cares about the
                // selection and whether a query is running, not about
                // the listings themselves.
                buildWhen: (PropertyState previous, PropertyState current) =>
                    previous.selectedAmenities != current.selectedAmenities ||
                    (previous is PropertyLoading) !=
                        (current is PropertyLoading),
                builder: (BuildContext context, PropertyState state) {
                  return PremiumFilterBar(
                    selected: state.selectedAmenities,
                    enabled: state is! PropertyLoading,
                    onToggle: (PropertyAmenity amenity) => context
                        .read<PropertyListingCubit>()
                        .toggleAmenity(amenity),
                  );
                },
              ),
              Expanded(
                child: BlocBuilder<PropertyListingCubit, PropertyState>(
                  builder: (BuildContext context, PropertyState state) {
                    return switch (state) {
                      PropertyLoading() => const _CenteredProgress(),
                      PropertyError(:final message) =>
                        _LoadFailure(message: message),
                      PropertyLoaded(isEmpty: true) => const _NoMatches(),
                      PropertyLoaded() => _ListingList(state: state),
                    };
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ListingList extends StatelessWidget {
  const _ListingList({required this.state});

  final PropertyLoaded state;

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.lg,
        AppSpacing.md,
        AppSpacing.lg,
        AppSpacing.xl,
      ),
      // One extra leading row for the results header, plus the showcase
      // notice when the listings are illustrative.
      itemCount: state.properties.length + (state.isShowcaseData ? 2 : 1),
      itemBuilder: (BuildContext context, int index) {
        if (index == 0) {
          return _ResultsHeader(count: state.properties.length);
        }
        if (state.isShowcaseData && index == 1) {
          return const _ShowcaseNotice();
        }

        final int offset = state.isShowcaseData ? 2 : 1;
        final Property property = state.properties[index - offset];
        return PropertyCard(property: property);
      },
    );
  }
}

class _ResultsHeader extends StatelessWidget {
  const _ResultsHeader({required this.count});

  final int count;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Row(
        children: <Widget>[
          Text(
            'العقارات المتاحة',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const Spacer(),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
            decoration: BoxDecoration(
              color: MizanColors.navy,
              borderRadius: BorderRadius.circular(AppRadius.card / 2),
            ),
            child: Text(
              '$count',
              style: const TextStyle(
                color: MizanColors.gold,
                fontSize: 12,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Says plainly that the listings are illustrative while the property
/// API does not exist yet, rather than letting sample data pass for
/// real inventory.
class _ShowcaseNotice extends StatelessWidget {
  const _ShowcaseNotice();

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: AppSpacing.md),
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: MizanColors.surface,
        borderRadius: AppRadius.cardRadius,
        border: Border.all(color: MizanColors.gold.withOpacity(0.35)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Icon(Icons.info_outline_rounded,
              size: 18, color: MizanColors.gold),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              'هذه عقارات تجريبية للعرض فقط، ريثما تصبح خدمة العقارات '
              'متاحة على الخادم.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        ],
      ),
    );
  }
}

class _CenteredProgress extends StatelessWidget {
  const _CenteredProgress();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: CircularProgressIndicator(
        valueColor: AlwaysStoppedAnimation<Color>(MizanColors.gold),
      ),
    );
  }
}

/// Shown when the selected filters exclude every listing — a legitimate
/// result, not a failure.
class _NoMatches extends StatelessWidget {
  const _NoMatches();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            CircleAvatar(
              radius: 30,
              backgroundColor: MizanColors.gold.withOpacity(0.14),
              child: const Icon(
                Icons.search_off_rounded,
                color: MizanColors.gold,
                size: 28,
              ),
            ),
            const SizedBox(height: AppSpacing.md),
            Text(
              'لا توجد عقارات مطابقة',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(
              'جرّب إزالة بعض عوامل التصفية لعرض المزيد.',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: AppSpacing.md),
            TextButton.icon(
              onPressed: () =>
                  context.read<PropertyListingCubit>().clearFilters(),
              icon: const Icon(Icons.filter_alt_off_outlined, size: 18),
              label: const Text('إزالة عوامل التصفية'),
              style: TextButton.styleFrom(foregroundColor: MizanColors.navy),
            ),
          ],
        ),
      ),
    );
  }
}

class _LoadFailure extends StatelessWidget {
  const _LoadFailure({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            const Icon(Icons.error_outline_rounded,
                color: MizanColors.error, size: 32),
            const SizedBox(height: AppSpacing.md),
            Text(
              message,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: AppSpacing.md),
            FilledButton.icon(
              onPressed: () =>
                  context.read<PropertyListingCubit>().loadProperties(),
              icon: const Icon(Icons.refresh_rounded, size: 18),
              label: const Text('إعادة المحاولة'),
            ),
          ],
        ),
      ),
    );
  }
}
