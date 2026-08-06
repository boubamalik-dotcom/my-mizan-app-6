import 'package:easy_localization/easy_localization.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/clinic.dart';
import '../providers/api_providers.dart';
import '../providers/patient_session_provider.dart';
import '../services/api_service.dart';
import 'queue_status_screen.dart';

enum _ConditionAnswer { routine, urgent }

/// Stable identity for each symptom, independent of its translated label
/// (which changes with the active language).
enum _Symptom {
  severePain('joinQueue.symptomSeverePain'),
  difficultyBreathing('joinQueue.symptomDifficultyBreathing'),
  highFever('joinQueue.symptomHighFever');

  final String translationKey;
  const _Symptom(this.translationKey);
}

class JoinQueueScreen extends ConsumerStatefulWidget {
  final Clinic clinic;

  const JoinQueueScreen({super.key, required this.clinic});

  @override
  ConsumerState<JoinQueueScreen> createState() => _JoinQueueScreenState();
}

class _JoinQueueScreenState extends ConsumerState<JoinQueueScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _nameController;
  late final TextEditingController _phoneController;

  _ConditionAnswer _condition = _ConditionAnswer.routine;
  final Set<_Symptom> _selectedSymptoms = {};

  bool _submitting = false;
  String? _errorMessage;

  bool get _isUrgent => _condition == _ConditionAnswer.urgent || _selectedSymptoms.isNotEmpty;

  @override
  void initState() {
    super.initState();
    final session = ref.read(patientSessionProvider);
    _nameController = TextEditingController(text: session.name ?? '');
    _phoneController = TextEditingController(text: session.phone ?? '');
  }

  @override
  void dispose() {
    _nameController.dispose();
    _phoneController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() {
      _submitting = true;
      _errorMessage = null;
    });

    final api = ref.read(apiServiceProvider);
    final sessionController = ref.read(patientSessionProvider.notifier);
    final name = _nameController.text.trim();
    final phone = _phoneController.text.trim();

    try {
      // A returning patient (same phone, possibly a new device) is reused
      // rather than re-registered, so POST /patients' unique-phone
      // constraint never blocks a legitimate visit.
      var patient = await api.findPatientByPhone(phone);
      patient ??= await api.registerPatient(name: name, phone: phone);
      await sessionController.savePatient(patient);

      final entry = await api.joinQueue(
        clinicId: widget.clinic.id,
        patientId: patient.id,
        isUrgent: _isUrgent,
      );
      await sessionController.setActiveQueue(clinicId: widget.clinic.id, queueEntryId: entry.id);

      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (_) => QueueStatusScreen(clinicId: widget.clinic.id, patientId: patient!.id),
        ),
      );
    } on ApiException catch (e) {
      setState(() => _errorMessage =
          'joinQueue.joinErrorWithStatus'.tr(namedArgs: {'status': '${e.statusCode}'}));
    } catch (_) {
      setState(() => _errorMessage = 'joinQueue.connectionError'.tr());
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(title: Text(widget.clinic.name)),
      body: SafeArea(
        child: Form(
          key: _formKey,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(
                widget.clinic.specialty,
                style: TextStyle(color: Colors.grey.shade600, fontWeight: FontWeight.w500),
              ),
              const SizedBox(height: 20),
              Text('joinQueue.yourDetails'.tr(),
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
              const SizedBox(height: 10),
              TextFormField(
                controller: _nameController,
                decoration: InputDecoration(
                  labelText: 'joinQueue.fullName'.tr(),
                  border: const OutlineInputBorder(),
                ),
                validator: (value) =>
                    (value == null || value.trim().isEmpty) ? 'joinQueue.fullNameRequired'.tr() : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _phoneController,
                keyboardType: TextInputType.phone,
                decoration: InputDecoration(
                  labelText: 'joinQueue.phone'.tr(),
                  border: const OutlineInputBorder(),
                ),
                validator: (value) =>
                    (value == null || value.trim().isEmpty) ? 'joinQueue.phoneRequired'.tr() : null,
              ),
              const SizedBox(height: 28),
              Text('joinQueue.quickTriage'.tr(),
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
              const SizedBox(height: 4),
              Text(
                'joinQueue.triageHelp'.tr(),
                style: TextStyle(color: Colors.grey.shade600, fontSize: 13),
              ),
              const SizedBox(height: 12),
              Text('joinQueue.conditionQuestion'.tr(),
                  style: const TextStyle(fontWeight: FontWeight.w600)),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: _ConditionChoiceCard(
                      label: 'joinQueue.routine'.tr(),
                      icon: Icons.event_available,
                      selected: _condition == _ConditionAnswer.routine,
                      onTap: () => setState(() => _condition = _ConditionAnswer.routine),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: _ConditionChoiceCard(
                      label: 'joinQueue.urgent'.tr(),
                      icon: Icons.warning_amber_rounded,
                      selected: _condition == _ConditionAnswer.urgent,
                      onTap: () => setState(() => _condition = _ConditionAnswer.urgent),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 20),
              Text(
                'joinQueue.symptomsQuestion'.tr(),
                style: const TextStyle(fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 4),
              Wrap(
                spacing: 8,
                runSpacing: 4,
                children: _Symptom.values.map((symptom) {
                  final selected = _selectedSymptoms.contains(symptom);
                  return FilterChip(
                    label: Text(symptom.translationKey.tr()),
                    selected: selected,
                    onSelected: (value) => setState(() {
                      if (value) {
                        _selectedSymptoms.add(symptom);
                      } else {
                        _selectedSymptoms.remove(symptom);
                      }
                    }),
                  );
                }).toList(),
              ),
              if (_isUrgent) ...[
                const SizedBox(height: 16),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.red.shade50,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: Colors.red.shade200),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.priority_high, color: Colors.red.shade700, size: 20),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'joinQueue.urgentWarning'.tr(),
                          style: TextStyle(color: Colors.red.shade700, fontWeight: FontWeight.w600),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
              if (_errorMessage != null) ...[
                const SizedBox(height: 16),
                Text(_errorMessage!, style: TextStyle(color: Colors.red.shade700)),
              ],
              const SizedBox(height: 28),
              SizedBox(
                height: 52,
                child: FilledButton.icon(
                  onPressed: _submitting ? null : _submit,
                  icon: _submitting
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                        )
                      : const Icon(Icons.confirmation_number_outlined),
                  label: Text(_submitting ? 'joinQueue.joining'.tr() : 'joinQueue.joinQueue'.tr()),
                  style: FilledButton.styleFrom(backgroundColor: Colors.teal.shade700),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ConditionChoiceCard extends StatelessWidget {
  final String label;
  final IconData icon;
  final bool selected;
  final VoidCallback onTap;

  const _ConditionChoiceCard({
    required this.label,
    required this.icon,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final color = selected ? Colors.teal.shade700 : Colors.grey.shade600;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 16),
        decoration: BoxDecoration(
          color: selected ? Colors.teal.shade50 : Colors.white,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: selected ? Colors.teal.shade400 : Colors.grey.shade300),
        ),
        child: Column(
          children: [
            Icon(icon, color: color),
            const SizedBox(height: 6),
            Text(label, style: TextStyle(color: color, fontWeight: FontWeight.w600)),
          ],
        ),
      ),
    );
  }
}
