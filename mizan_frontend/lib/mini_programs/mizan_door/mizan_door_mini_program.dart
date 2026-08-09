import 'package:flutter/material.dart';

import '../../core/mini_program_loader/mini_program_base.dart';
import 'presentation/pages/queue_dashboard_page.dart';

/// Entry point for the Mizan Door mini-program: clinic queue
/// reservations and live wait-time displays.
///
/// STRICT SCOPE RULE: Mizan Door is limited to clinic queue management
/// and wait-time UI only. It must never contain QR-code scanning or
/// payment-related folders, files, widgets, or logic — that
/// functionality belongs to the core Digital Wallet feature
/// (`lib/core/wallet/`), not to this mini-program.
///
/// This class is the only piece of Mizan Door that the host shell
/// (registry, loader, navigator) ever references directly. Its
/// feature UI lives under `presentation/`, domain rules under
/// `domain/`, and persistence under `data/`, fully isolated from the
/// other mini-programs.
///
/// [buildRootWidget] returns the same `QueueDashboardPage` that
/// `CoreRoutes.mizanDoor` renders, so reaching the mini-program through
/// the loader and reaching it by route land on one screen rather than
/// diverging.
class MizanDoorMiniProgram extends BaseMiniProgram {
  @override
  String get id => 'mizan_door';

  @override
  String get title => 'Mizan Door';

  @override
  String get description => 'Clinic queue reservations & wait times';

  @override
  IconData get icon => Icons.hourglass_bottom_rounded;

  @override
  Color get accentColor => const Color(0xFF1565C0);

  @override
  Widget buildRootWidget(BuildContext context) {
    return const QueueDashboardPage();
  }
}
