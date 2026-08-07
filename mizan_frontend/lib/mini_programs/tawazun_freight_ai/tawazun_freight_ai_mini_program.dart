import 'package:flutter/material.dart';

import '../../core/mini_program_loader/mini_program_base.dart';
import '../../shared/design_system/widgets/mini_program_placeholder_page.dart';

/// Entry point for the Tawazun Freight AI mini-program: AI-assisted
/// logistics, freight tracking, and supply-chain visibility.
///
/// This class is the only piece of Tawazun Freight AI that the host
/// shell (registry, loader, navigator) ever references directly. Its
/// feature UI lives under `presentation/`, domain rules under
/// `domain/`, and persistence under `data/`, fully isolated from the
/// other mini-programs — none of that is imported here yet, so this
/// entry point currently renders a placeholder page.
class TawazunFreightAiMiniProgram extends BaseMiniProgram {
  @override
  String get id => 'tawazun_freight_ai';

  @override
  String get title => 'Tawazun Freight AI';

  @override
  String get description => 'AI-powered logistics & freight tracking';

  @override
  IconData get icon => Icons.local_shipping_outlined;

  @override
  Color get accentColor => const Color(0xFF2E7D32);

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
