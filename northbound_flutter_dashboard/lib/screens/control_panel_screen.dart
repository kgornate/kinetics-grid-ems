import 'package:flutter/material.dart';

import '../api/northbound_api_client.dart';
import '../models/control_command_result.dart';
import '../models/source_summary.dart';
import '../widgets/json_viewer.dart';
import '../widgets/status_chip.dart';

class ControlPanelScreen extends StatefulWidget {
  const ControlPanelScreen({super.key, required this.apiClient});

  final NorthboundApiClient apiClient;

  @override
  State<ControlPanelScreen> createState() => _ControlPanelScreenState();
}

class _ControlPanelScreenState extends State<ControlPanelScreen> {
  List<SourceSummary> sources = [];
  String? selectedSourceId;
  String? error;
  bool loading = false;
  bool commandRunning = false;
  Map<String, dynamic>? lastResult;
  final powerController = TextEditingController(text: '5');
  bool readback = true;
  bool waitForVoltageStable = true;

  List<String> get sourceIds => sources.map((s) => s.sourceId).toList();

  @override
  void initState() {
    super.initState();
    refresh();
  }

  @override
  void dispose() {
    powerController.dispose();
    super.dispose();
  }

  Future<void> refresh() async {
    setState(() {
      loading = true;
      error = null;
    });
    final result = await widget.apiClient.getSourceSummary();
    if (!mounted) return;
    setState(() {
      loading = false;
      if (result.isSuccess) {
        sources = result.data ?? [];
        if (sources.isNotEmpty && !sources.any((s) => s.sourceId == selectedSourceId)) {
          selectedSourceId = sources.first.sourceId;
        }
      } else {
        error = result.error;
      }
    });
  }

  Future<void> _run(String label, Future<dynamic> Function() action) async {
    setState(() {
      commandRunning = true;
      error = null;
      lastResult = null;
    });
    try {
      final result = await action();
      if (!mounted) return;
      setState(() {
        commandRunning = false;
        if (result.isSuccess) {
          final data = result.data;
          if (data is ControlCommandResult) {
            lastResult = data.raw;
          } else if (data is Map<String, dynamic>) {
            lastResult = data;
          } else {
            lastResult = {'ok': true, 'message': '$label completed', 'data': data.toString()};
          }
        } else {
          error = result.error ?? '$label failed';
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        commandRunning = false;
        error = '$label failed: $e';
      });
    }
  }

  num _powerKw() => num.tryParse(powerController.text.trim()) ?? 0;

  @override
  Widget build(BuildContext context) {
    final selected = selectedSourceId;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Internal Control Panel'),
        actions: [IconButton(onPressed: refresh, icon: const Icon(Icons.refresh))],
      ),
      body: RefreshIndicator(
        onRefresh: refresh,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                StatusChip(label: '${sources.length} sources', good: sources.isNotEmpty),
                StatusChip(label: sources.every((s) => s.online) ? 'All online' : 'Check source', good: sources.every((s) => s.online)),
                StatusChip(label: 'Internal write APIs', good: true, icon: Icons.lock_open),
              ],
            ),
            const SizedBox(height: 12),
            if (loading) const LinearProgressIndicator(),
            if (error != null) Card(child: ListTile(leading: const Icon(Icons.error_outline), title: Text(error!))),
            _sourceSelector(),
            const SizedBox(height: 12),
            _singleSourceControls(selected),
            const SizedBox(height: 12),
            _siteControls(),
            const SizedBox(height: 12),
            _resultPanel(),
          ],
        ),
      ),
    );
  }

  Widget _sourceSelector() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Source selection', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 10),
            DropdownButtonFormField<String>(
              value: selectedSourceId,
              decoration: const InputDecoration(labelText: 'Target EMS source'),
              items: [
                for (final source in sources)
                  DropdownMenuItem(
                    value: source.sourceId,
                    child: Text('${source.displayName}  ${source.host}:${source.port}'),
                  ),
              ],
              onChanged: commandRunning ? null : (value) => setState(() => selectedSourceId = value),
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final source in sources)
                  Chip(
                    avatar: Icon(source.online ? Icons.check_circle : Icons.error, size: 16),
                    label: Text('${source.sourceId}: ${source.signalCount} signals, bad ${source.badSignalCount}'),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _singleSourceControls(String? selected) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Single EMS commands', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 6),
            Text('These buttons call high-level backend control APIs. Start with standby before grid or power commands.', style: Theme.of(context).textTheme.bodyMedium),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                FilledButton.icon(
                  onPressed: selected == null || commandRunning ? null : () => _run('Standby', () => widget.apiClient.standbySource(sourceId: selected, readback: readback, note: 'Flutter standby')), 
                  icon: const Icon(Icons.pause_circle),
                  label: const Text('Standby / zero power'),
                ),
                OutlinedButton.icon(
                  onPressed: selected == null || commandRunning ? null : () => _run('Grid-tied', () => widget.apiClient.setSourceGridMode(sourceId: selected, targetMode: 'grid_tied', readback: readback, note: 'Flutter grid tied')), 
                  icon: const Icon(Icons.grid_on),
                  label: const Text('Switch grid-tied'),
                ),
                OutlinedButton.icon(
                  onPressed: selected == null || commandRunning ? null : () => _confirmDanger(
                    title: 'Switch selected EMS to off-grid?',
                    message: 'This writes the vendor off-grid command for $selected. Continue only with site permission.',
                    onConfirm: () => _run('Off-grid', () => widget.apiClient.setSourceGridMode(sourceId: selected, targetMode: 'off_grid', readback: readback, note: 'Flutter off grid')),
                  ),
                  icon: const Icon(Icons.power_settings_new),
                  label: const Text('Switch off-grid'),
                ),
              ],
            ),
            const Divider(height: 28),
            Wrap(
              spacing: 12,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                SizedBox(
                  width: 160,
                  child: TextField(
                    controller: powerController,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(labelText: 'Power kW'),
                  ),
                ),
                FilledButton.tonalIcon(
                  onPressed: selected == null || commandRunning || _powerKw() <= 0 ? null : () => _confirmDanger(
                    title: 'Charge selected EMS?',
                    message: 'This writes manual charge power ${_powerKw()} kW to $selected.',
                    onConfirm: () => _run('Charge', () => widget.apiClient.chargeSource(sourceId: selected, powerKw: _powerKw(), readback: readback, note: 'Flutter charge')),
                  ),
                  icon: const Icon(Icons.battery_charging_full),
                  label: const Text('Charge'),
                ),
                FilledButton.tonalIcon(
                  onPressed: selected == null || commandRunning || _powerKw() <= 0 ? null : () => _confirmDanger(
                    title: 'Discharge selected EMS?',
                    message: 'This writes manual discharge power ${_powerKw()} kW to $selected.',
                    onConfirm: () => _run('Discharge', () => widget.apiClient.dischargeSource(sourceId: selected, powerKw: _powerKw(), readback: readback, note: 'Flutter discharge')),
                  ),
                  icon: const Icon(Icons.bolt),
                  label: const Text('Discharge'),
                ),
                FilterChip(label: const Text('Readback'), selected: readback, onSelected: commandRunning ? null : (v) => setState(() => readback = v)),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _siteControls() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Both EMS site commands', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 6),
            Text('Grid-tied can be issued to both. Off-grid is sequential using EMS1 then EMS2 and voltage-stability waiting.', style: Theme.of(context).textTheme.bodyMedium),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                FilledButton.icon(
                  onPressed: sourceIds.isEmpty || commandRunning ? null : () => _run('Site standby', () => widget.apiClient.standbySite(sourceIds: sourceIds, readback: readback, note: 'Flutter site standby')),
                  icon: const Icon(Icons.pause_circle_outline),
                  label: const Text('Both standby'),
                ),
                OutlinedButton.icon(
                  onPressed: sourceIds.isEmpty || commandRunning ? null : () => _run('Site grid-tied', () => widget.apiClient.setSiteGridMode(targetMode: 'grid_tied', sourceIds: sourceIds, readback: readback, note: 'Flutter both grid tied')),
                  icon: const Icon(Icons.grid_on),
                  label: const Text('Both grid-tied'),
                ),
                OutlinedButton.icon(
                  onPressed: sourceIds.length < 2 || commandRunning ? null : () => _confirmDanger(
                    title: 'Switch both EMS to off-grid sequentially?',
                    message: 'Sequence: ${sourceIds.join(' → ')}. Backend waits for off-grid status and voltage stabilization using 346/348/350.',
                    onConfirm: () => _run('Site off-grid', () => widget.apiClient.setSiteGridMode(targetMode: 'off_grid', sourceOrder: sourceIds, readback: readback, waitForVoltageStable: waitForVoltageStable, note: 'Flutter both off grid sequential')),
                  ),
                  icon: const Icon(Icons.power_settings_new),
                  label: const Text('Both off-grid sequential'),
                ),
                FilterChip(label: const Text('Wait voltage stable'), selected: waitForVoltageStable, onSelected: commandRunning ? null : (v) => setState(() => waitForVoltageStable = v)),
              ],
            ),
            const Divider(height: 28),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                FilledButton.tonalIcon(
                  onPressed: sourceIds.isEmpty || commandRunning || _powerKw() <= 0 ? null : () => _confirmDanger(
                    title: 'Charge both EMS?',
                    message: 'Total charge command ${_powerKw()} kW with equal allocation across ${sourceIds.length} sources.',
                    onConfirm: () => _run('Site charge', () => widget.apiClient.setSitePower(operation: 'charge', totalPowerKw: _powerKw(), sourceIds: sourceIds, readback: readback, note: 'Flutter both charge')),
                  ),
                  icon: const Icon(Icons.battery_charging_full),
                  label: const Text('Both charge equal'),
                ),
                FilledButton.tonalIcon(
                  onPressed: sourceIds.isEmpty || commandRunning || _powerKw() <= 0 ? null : () => _confirmDanger(
                    title: 'Discharge both EMS?',
                    message: 'Total discharge command ${_powerKw()} kW with equal allocation across ${sourceIds.length} sources.',
                    onConfirm: () => _run('Site discharge', () => widget.apiClient.setSitePower(operation: 'discharge', totalPowerKw: _powerKw(), sourceIds: sourceIds, readback: readback, note: 'Flutter both discharge')),
                  ),
                  icon: const Icon(Icons.bolt),
                  label: const Text('Both discharge equal'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _resultPanel() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text('Last command result', style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(width: 8),
                if (commandRunning) const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
              ],
            ),
            const SizedBox(height: 8),
            if (lastResult == null)
              const Text('No command executed yet in this screen.')
            else
              JsonViewer(data: lastResult!),
          ],
        ),
      ),
    );
  }

  Future<void> _confirmDanger({required String title, required String message, required VoidCallback onConfirm}) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: Text(message),
        actions: [
          TextButton(onPressed: () => Navigator.of(context).pop(false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.of(context).pop(true), child: const Text('Confirm')),
        ],
      ),
    );
    if (ok == true) onConfirm();
  }
}
