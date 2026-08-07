import 'package:flutter/material.dart';

import 'core/core_navigator.dart';

void main() {
  runApp(const MizanApp());
}

/// Root widget of the Mizan Super App.
///
/// Wires the Host Shell's routing table ([CoreNavigator]) into
/// [MaterialApp]. All navigation — to the dashboard, and to any
/// dynamically-loaded mini-program — flows through
/// [CoreNavigator.onGenerateRoute].
class MizanApp extends StatelessWidget {
  const MizanApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Mizan',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorSchemeSeed: const Color(0xFF1565C0),
      ),
      initialRoute: CoreRoutes.dashboard,
      onGenerateRoute: CoreNavigator.onGenerateRoute,
    );
  }
}
