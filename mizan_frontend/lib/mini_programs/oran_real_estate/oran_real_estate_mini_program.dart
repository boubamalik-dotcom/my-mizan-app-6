import 'package:flutter/material.dart';

import '../../core/mini_program_loader/mini_program_base.dart';
import '../../shared/design_system/widgets/mini_program_placeholder_page.dart';

/// Entry point for the Oran Real Estate mini-program: property
/// listings, virtual tours, and agent contact.
///
/// This class is the only piece of Oran Real Estate that the host
/// shell (registry, loader, navigator) ever references directly. Its
/// feature UI lives under `presentation/`, domain rules under
/// `domain/`, and persistence under `data/`, fully isolated from the
/// other mini-programs — none of that is imported here yet, so this
/// entry point currently renders a placeholder page.
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
    return MiniProgramPlaceholderPage(
      title: title,
      description: description,
      icon: icon,
      accentColor: accentColor,
    );
  }
}
