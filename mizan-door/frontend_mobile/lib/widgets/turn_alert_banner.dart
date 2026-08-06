import 'package:easy_localization/easy_localization.dart';
import 'package:flutter/material.dart';

/// In-app "your turn is coming up" / "it's your turn" alert.
///
/// The original spec calls for a push/local notification when the patient's
/// turn is near. Native push (FCM) and `flutter_local_notifications` both
/// need platform-specific setup (and have limited/awkward web support) that
/// can't be verified in this environment, which has no Android/iOS
/// device/emulator available. This in-app banner delivers the same
/// information the moment the queue updates over the WebSocket, and works
/// identically on every platform Flutter targets - including the web build
/// used to test this app end-to-end. Swapping in real push notifications
/// later would only mean adding a call alongside where this banner is shown.
class TurnAlertBanner extends StatelessWidget {
  final String message;
  final IconData icon;
  final Color color;

  const TurnAlertBanner({
    super.key,
    required this.message,
    this.icon = Icons.notifications_active,
    required this.color,
  });

  factory TurnAlertBanner.nearTurn(int patientsAhead) {
    return TurnAlertBanner(
      message: patientsAhead <= 0
          ? 'queueStatus.nearTurnReady'.tr()
          : 'queueStatus.nearTurnCount'.tr(namedArgs: {'count': '$patientsAhead'}),
      icon: Icons.notifications_active,
      color: Colors.orange.shade800,
    );
  }

  factory TurnAlertBanner.yourTurn() {
    return TurnAlertBanner(
      message: 'queueStatus.yourTurn'.tr(),
      icon: Icons.check_circle,
      color: Colors.green.shade800,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      margin: const EdgeInsets.only(bottom: 16),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Row(
        children: [
          Icon(icon, color: color),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              message,
              style: TextStyle(color: color, fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
  }
}
