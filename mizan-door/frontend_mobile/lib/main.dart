import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'providers/patient_session_provider.dart';
import 'screens/clinic_select_screen.dart';
import 'screens/queue_status_screen.dart';

void main() {
  runApp(const ProviderScope(child: MizanDoorApp()));
}

class MizanDoorApp extends StatelessWidget {
  const MizanDoorApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Mizan Door',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.teal),
        useMaterial3: true,
      ),
      home: const AppRoot(),
    );
  }
}

/// Decides whether to resume an in-progress queue visit or start fresh at
/// clinic selection, based on the persisted patient session.
class AppRoot extends ConsumerWidget {
  const AppRoot({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(patientSessionProvider);

    if (!session.loaded) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    if (session.hasActiveQueue) {
      return QueueStatusScreen(
        clinicId: session.activeClinicId!,
        patientId: session.patientId!,
      );
    }

    return const ClinicSelectScreen();
  }
}
