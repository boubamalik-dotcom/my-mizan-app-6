import 'package:easy_localization/easy_localization.dart';
import 'package:flutter/material.dart';

import '../providers/queue_controller.dart';

class ConnectionStatusChip extends StatelessWidget {
  final ConnectionStatus status;

  const ConnectionStatusChip({super.key, required this.status});

  @override
  Widget build(BuildContext context) {
    final isOpen = status == ConnectionStatus.open;
    final color = isOpen ? Colors.green.shade700 : Colors.orange.shade800;
    final background = isOpen ? Colors.green.shade50 : Colors.orange.shade50;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(isOpen ? Icons.wifi : Icons.wifi_off, size: 12, color: color),
          const SizedBox(width: 4),
          Text(
            isOpen ? 'connection.live'.tr() : 'connection.reconnecting'.tr(),
            style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: color),
          ),
        ],
      ),
    );
  }
}
