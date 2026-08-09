import 'package:flutter/material.dart';

import '../../core/mini_program_loader/mini_program_base.dart';
import 'presentation/pages/property_listing_page.dart';

/// Entry point for the Oran Real Estate mini-program: property
/// listings, virtual tours, and agent contact.
///
/// This class is the only piece of Oran Real Estate that the host
/// shell (registry, loader, navigator) ever references directly. Its
/// feature UI lives under `presentation/`, domain rules under
/// `domain/`, and persistence under `data/`, fully isolated from the
/// other mini-programs.
///
/// [buildRootWidget] returns the same `PropertyListingPage` that
/// `CoreRoutes.realEstate` renders, so reaching the mini-program
/// through the loader and reaching it by route land on one screen
/// rather than diverging.
class OranRealEstateMiniProgram extends BaseMiniProgram {
  @override
  String get id => 'oran_real_estate';

  @override
  String get title => 'Oran Real Estate';

  @override
  String get description => 'Property listings, tours & agent contact';

  @override
  IconData get icon => Icons.apartment_outlined;

  @override
  Color get accentColor => const Color(0xFF6A1B9A);

  @override
  Widget buildRootWidget(BuildContext context) {
    return const PropertyListingPage();
  }
}
