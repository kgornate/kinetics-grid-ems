import 'dart:convert';

import 'package:flutter/material.dart';

import '../core/state/gateway_controller.dart';
import '../widgets/common_widgets.dart';

class DiagnosticsScreen extends StatefulWidget {
  const DiagnosticsScreen({super.key, required this.controller});

  final GatewayController controller;

  @override
  State<DiagnosticsScreen> createState() => _DiagnosticsScreenState();
}

class _DiagnosticsScreenState extends State<DiagnosticsScreen> {
  bool _scenarioLoading = false;
  List<String> _scenarios = const <String>[];
  String? _selectedScenario;

  Future<void> _loadScenarios() async {
    setState(() => _scenarioLoading = true);
    try {
      final result = await widget.controller.loadMockScenarios();
      final raw = result['scenarios'];
      if (raw is List) {
        _scenarios = raw.map((item) => item.toString()).toList();
      }
      _selectedScenario = result['current']?.toString();
    } catch (_) {
      _scenarios = const <String>[];
    } finally {
      if (mounted) setState(() => _scenarioLoading = false);
    }
  }

  @override
  void initState() {
    super.initState();
    if (widget.controller.plant.mode == 'mock' || widget.controller.plant.mode == 'mixed') {
      _loadScenarios();
    }
  }

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        SectionHeader(
          'Gateway diagnostics',
          subtitle: 'Connectivity, polling scheduler, storage and data-rate information.',
          trailing: FilledButton.tonalIcon(
            onPressed: () => controller.refreshDiagnostics(),
            icon: const Icon(Icons.refresh),
            label: const Text('Refresh'),
          ),
        ),
        const SizedBox(height: 16),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: [
            StatusPill(label: controller.restConnected ? 'REST connected' : 'REST offline', good: controller.restConnected),
            StatusPill(label: controller.wsConnected ? 'WebSocket connected' : 'WebSocket offline', good: controller.wsConnected),
            StatusPill(label: 'Role ${controller.session?.role ?? '--'}', good: true, icon: Icons.verified_user),
            StatusPill(label: 'Mode ${controller.plant.mode}', good: true, icon: Icons.settings),
          ],
        ),
        const SizedBox(height: 16),
        Card(
          child: ListTile(
            leading: const Icon(Icons.link),
            title: const Text('Current API endpoint'),
            subtitle: SelectableText(controller.session?.baseUrl ?? '--'),
          ),
        ),
        const SizedBox(height: 16),
        if (controller.isInternal && (controller.plant.mode == 'mock' || controller.plant.mode == 'mixed')) ...[
          SectionHeader('Mock scenario control', subtitle: 'Available only when the gateway is running in mock or mixed mode.'),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: DropdownButtonFormField<String>(
                  value: _scenarios.contains(_selectedScenario) ? _selectedScenario : null,
                  decoration: const InputDecoration(labelText: 'Scenario', border: OutlineInputBorder()),
                  items: _scenarios.map((item) => DropdownMenuItem(value: item, child: Text(item))).toList(),
                  onChanged: _scenarioLoading ? null : (value) => setState(() => _selectedScenario = value),
                ),
              ),
              const SizedBox(width: 12),
              FilledButton.icon(
                onPressed: _selectedScenario == null
                    ? null
                    : () async {
                        await controller.setMockScenario(_selectedScenario!);
                        if (mounted) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(content: Text(controller.lastEventMessage ?? 'Scenario changed')),
                          );
                        }
                      },
                icon: const Icon(Icons.science),
                label: const Text('Apply'),
              ),
            ],
          ),
          const SizedBox(height: 20),
        ],
        SectionHeader('Complete extraction test'),
        const SizedBox(height: 10),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                const Expanded(
                  child: Text('Trigger one complete BMS read cycle: fast, normal, slow and bulk arrays. Use this during commissioning, not continuously.'),
                ),
                const SizedBox(width: 16),
                FilledButton.icon(
                  onPressed: controller.busy ? null : () => controller.forceCompleteExtraction(),
                  icon: const Icon(Icons.download_for_offline),
                  label: const Text('Run total extraction'),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 20),
        _JsonPanel(title: 'Health', value: controller.health),
        _JsonPanel(title: 'Polling scheduler', value: controller.polling),
        _JsonPanel(title: 'Storage', value: controller.storage),
        _JsonPanel(title: 'Data rate', value: controller.dataRate),
        if (controller.errorMessage != null)
          Card(
            color: Theme.of(context).colorScheme.errorContainer,
            child: ListTile(
              leading: const Icon(Icons.error_outline),
              title: const Text('Latest error'),
              subtitle: SelectableText(controller.errorMessage!),
            ),
          ),
        const SizedBox(height: 30),
      ],
    );
  }
}

class _JsonPanel extends StatelessWidget {
  const _JsonPanel({required this.title, required this.value});

  final String title;
  final Map<String, dynamic> value;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 14),
      child: ExpansionTile(
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
        subtitle: Text(value.isEmpty ? 'No data' : '${value.length} top-level fields'),
        children: [
          Container(
            width: double.infinity,
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            child: SelectableText(
              const JsonEncoder.withIndent('  ').convert(value),
              style: const TextStyle(fontFamily: 'monospace'),
            ),
          ),
        ],
      ),
    );
  }
}
