// easy_localization re-exports package:intl, which has its own TextDirection
// class that would otherwise collide with Flutter's (used below for the
// RTL-aware chevron icon).
import 'package:easy_localization/easy_localization.dart' hide TextDirection;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/clinic.dart';
import '../providers/api_providers.dart';
import '../widgets/language_toggle.dart';
import 'join_queue_screen.dart';

class ClinicSelectScreen extends ConsumerWidget {
  const ClinicSelectScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final clinicsAsync = ref.watch(clinicsProvider);

    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        title: Text('app.name'.tr()),
        centerTitle: false,
        actions: const [
          Padding(padding: EdgeInsetsDirectional.only(end: 12), child: LanguageToggle()),
        ],
      ),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: () => ref.refresh(clinicsProvider.future),
          child: clinicsAsync.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (error, _) => _ErrorState(onRetry: () => ref.invalidate(clinicsProvider)),
            data: (clinics) => _ClinicList(clinics: clinics),
          ),
        ),
      ),
    );
  }
}

class _ClinicList extends StatelessWidget {
  final List<Clinic> clinics;

  const _ClinicList({required this.clinics});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Padding(
          padding: const EdgeInsets.only(bottom: 12, top: 4),
          child: Text(
            'clinicSelect.title'.tr(),
            style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
          ),
        ),
        if (clinics.isEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 32),
            child: Center(
              child: Text(
                'clinicSelect.noClinics'.tr(),
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.black54),
              ),
            ),
          )
        else
          ...clinics.map(
            (clinic) => Card(
              margin: const EdgeInsets.only(bottom: 10),
              elevation: 0,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(14),
                side: BorderSide(color: Colors.grey.shade200),
              ),
              child: ListTile(
                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                leading: CircleAvatar(
                  backgroundColor: Colors.teal.shade50,
                  child: Icon(Icons.local_hospital, color: Colors.teal.shade700),
                ),
                title: Text(clinic.name, style: const TextStyle(fontWeight: FontWeight.w600)),
                subtitle: Text(clinic.specialty),
                trailing: Icon(
                  Directionality.of(context) == TextDirection.rtl
                      ? Icons.chevron_left
                      : Icons.chevron_right,
                ),
                onTap: () {
                  Navigator.of(context).push(
                    MaterialPageRoute(builder: (_) => JoinQueueScreen(clinic: clinic)),
                  );
                },
              ),
            ),
          ),
      ],
    );
  }
}

class _ErrorState extends StatelessWidget {
  final VoidCallback onRetry;

  const _ErrorState({required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.cloud_off, size: 40, color: Colors.grey.shade400),
            const SizedBox(height: 12),
            Text('clinicSelect.connectionError'.tr(), textAlign: TextAlign.center),
            const SizedBox(height: 16),
            FilledButton(onPressed: onRetry, child: Text('clinicSelect.retry'.tr())),
          ],
        ),
      ),
    );
  }
}
