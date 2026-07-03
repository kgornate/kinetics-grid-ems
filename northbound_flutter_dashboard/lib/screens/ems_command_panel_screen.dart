import 'package:flutter/material.dart';

import '../api/northbound_api_client.dart';
import '../models/auth_session.dart';
import '../models/ems_command_register.dart';
import '../widgets/json_viewer.dart';

class EmsCommandPanelScreen extends StatefulWidget {
  const EmsCommandPanelScreen({super.key, required this.apiClient, required this.authSession});

  final NorthboundApiClient apiClient;
  final AuthSession authSession;

  @override
  State<EmsCommandPanelScreen> createState() => _EmsCommandPanelScreenState();
}

class _EmsCommandPanelScreenState extends State<EmsCommandPanelScreen> {
  final searchController = TextEditingController();
  final valueController = TextEditingController();
  final noteController = TextEditingController();
  List<EmsCommandRegister> registers = [];
  EmsCommandRegister? selected;
  Map<String, dynamic>? lastResult;
  String? error;
  String? categoryFilter;
  bool loading = false;
  bool writing = false;
  bool readback = true;

  @override
  void initState() {
    super.initState();
    loadRegisters();
  }

  @override
  void dispose() {
    searchController.dispose();
    valueController.dispose();
    noteController.dispose();
    super.dispose();
  }

  Future<void> loadRegisters() async {
    setState(() {
      loading = true;
      error = null;
    });
    final result = await widget.apiClient.getEmsCommandRegisters();
    if (!mounted) return;
    setState(() {
      loading = false;
      if (result.isSuccess) {
        registers = result.data ?? [];
        selected ??= registers.isNotEmpty ? registers.first : null;
        if (selected != null && valueController.text.trim().isEmpty && selected!.latestValue != null) {
          valueController.text = _formatDouble(selected!.latestValue!);
        }
      } else {
        error = result.error;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.authSession.isInternalAdmin) {
      return Scaffold(
        appBar: AppBar(title: const Text('EMS Command Panel')),
        body: const Center(child: Text('This panel is available only for internal_admin login.')),
      );
    }

    final filtered = _filteredRegisters();
    final categories = registers.map((r) => r.category).where((c) => c.trim().isNotEmpty).toSet().toList()..sort();

    return Scaffold(
      appBar: AppBar(
        title: const Text('EMS Command Panel'),
        actions: [
          IconButton(tooltip: 'Refresh registers', icon: const Icon(Icons.refresh), onPressed: loadRegisters),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: loadRegisters,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _safetyCard(),
            const SizedBox(height: 12),
            if (loading) const LinearProgressIndicator(),
            if (error != null) Card(child: ListTile(leading: const Icon(Icons.error_outline), title: Text(error!))),
            _writeCard(),
            const SizedBox(height: 16),
            Row(
              children: [
                Text('EMS writable registers', style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(width: 8),
                Chip(label: Text('${filtered.length}/${registers.length}')),
              ],
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                SizedBox(
                  width: 360,
                  child: TextField(
                    controller: searchController,
                    decoration: const InputDecoration(
                      border: OutlineInputBorder(),
                      prefixIcon: Icon(Icons.search),
                      labelText: 'Search name, signal, address or description',
                    ),
                    onChanged: (_) => setState(() {}),
                  ),
                ),
                DropdownButton<String?>(
                  value: categoryFilter,
                  hint: const Text('All categories'),
                  items: [
                    const DropdownMenuItem<String?>(value: null, child: Text('All categories')),
                    for (final category in categories) DropdownMenuItem<String?>(value: category, child: Text(category)),
                  ],
                  onChanged: (value) => setState(() => categoryFilter = value),
                ),
              ],
            ),
            const SizedBox(height: 8),
            for (final register in filtered) _registerTile(register),
            if (filtered.isEmpty && !loading) const Card(child: ListTile(title: Text('No EMS command register matched the current filter.'))),
            if (lastResult != null) ...[
              const SizedBox(height: 16),
              ExpansionTile(title: const Text('Last command API response'), children: [JsonViewer(data: lastResult!)]),
            ],
          ],
        ),
      ),
    );
  }

  Widget _safetyCard() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.admin_panel_settings_outlined),
                const SizedBox(width: 8),
                Text('Internal EMS write access', style: Theme.of(context).textTheme.titleLarge),
              ],
            ),
            const SizedBox(height: 8),
            const Text(
              'This panel exposes only EMS asset registers where asset_id = ems_system and R/W = 1 in the northbound register table. '
              'Customer users cannot open or call these command APIs.',
            ),
          ],
        ),
      ),
    );
  }

  Widget _writeCard() {
    final r = selected;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Write EMS Register', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 12),
            if (r == null)
              const Text('No writable EMS registers loaded yet.')
            else ...[
              Text(r.pointName, style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 4),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  Chip(label: Text('signal: ${r.signalName}')),
                  Chip(label: Text('address: ${r.address}')),
                  Chip(label: Text('qty: ${r.registerQty}')),
                  Chip(label: Text('category: ${r.category}')),
                  if (r.unit.isNotEmpty) Chip(label: Text('unit: ${r.unit}')),
                  if (r.latestValue != null) Chip(label: Text('latest: ${_formatDouble(r.latestValue!)} ${r.unit}')),
                ],
              ),
              if (r.description.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 8), child: Text(r.description)),
              const SizedBox(height: 12),
              Wrap(
                spacing: 12,
                runSpacing: 12,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  SizedBox(
                    width: 260,
                    child: TextField(
                      controller: valueController,
                      keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
                      decoration: InputDecoration(border: const OutlineInputBorder(), labelText: 'Value to write', helperText: r.valueHint),
                    ),
                  ),
                  SizedBox(
                    width: 320,
                    child: TextField(
                      controller: noteController,
                      decoration: const InputDecoration(border: OutlineInputBorder(), labelText: 'Operator note / reason'),
                    ),
                  ),
                  FilterChip(label: const Text('Read back after write'), selected: readback, onSelected: (v) => setState(() => readback = v)),
                  FilledButton.icon(
                    onPressed: writing ? null : _confirmAndWrite,
                    icon: writing ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.send),
                    label: const Text('Write command'),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _registerTile(EmsCommandRegister register) {
    final isSelected = selected?.signalName == register.signalName;
    return Card(
      child: ListTile(
        selected: isSelected,
        leading: CircleAvatar(child: Text(register.address.toString())),
        title: Text(register.pointName),
        subtitle: Text('${register.signalName} • ${register.category}${register.description.isNotEmpty ? ' • ${register.description}' : ''}'),
        trailing: Wrap(
          spacing: 8,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            if (register.latestValue != null) Text('latest ${_formatDouble(register.latestValue!)} ${register.unit}'),
            OutlinedButton(onPressed: () => _select(register), child: Text(isSelected ? 'Selected' : 'Select')),
          ],
        ),
        onTap: () => _select(register),
      ),
    );
  }

  void _select(EmsCommandRegister register) {
    setState(() {
      selected = register;
      if (register.latestValue != null) {
        valueController.text = _formatDouble(register.latestValue!);
      } else {
        valueController.clear();
      }
    });
  }

  Future<void> _confirmAndWrite() async {
    final r = selected;
    if (r == null) return;
    final value = double.tryParse(valueController.text.trim());
    if (value == null) {
      setState(() => error = 'Please enter a numeric value.');
      return;
    }

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Confirm EMS register write'),
        content: Text('Write ${_formatDouble(value)} ${r.unit} to ${r.pointName} at address ${r.address}?'),
        actions: [
          TextButton(onPressed: () => Navigator.of(context).pop(false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.of(context).pop(true), child: const Text('Write')),
        ],
      ),
    );
    if (confirmed != true) return;

    setState(() {
      writing = true;
      error = null;
      lastResult = null;
    });
    final result = await widget.apiClient.writeEmsCommand(
      signalName: r.signalName,
      value: value,
      readback: readback,
      note: noteController.text.trim().isEmpty ? null : noteController.text.trim(),
    );
    if (!mounted) return;
    if (result.isSuccess) {
      setState(() {
        writing = false;
        lastResult = result.data;
      });
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Command written: ${r.signalName}')));
      await loadRegisters();
    } else {
      setState(() {
        writing = false;
        error = result.error;
      });
    }
  }

  List<EmsCommandRegister> _filteredRegisters() {
    final q = searchController.text.trim().toLowerCase();
    return registers.where((r) {
      final matchesCategory = categoryFilter == null || r.category == categoryFilter;
      if (!matchesCategory) return false;
      if (q.isEmpty) return true;
      return r.pointName.toLowerCase().contains(q) ||
          r.signalName.toLowerCase().contains(q) ||
          r.description.toLowerCase().contains(q) ||
          r.address.toString().contains(q);
    }).toList();
  }

  String _formatDouble(double value) {
    if (value == value.roundToDouble()) return value.toStringAsFixed(0);
    return value.toStringAsFixed(4).replaceFirst(RegExp(r'0+$'), '').replaceFirst(RegExp(r'\.$'), '');
  }
}
