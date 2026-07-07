import 'package:flutter/material.dart';

import '../api/northbound_api_client.dart';
import '../models/ems_command_register.dart';
import '../models/source_summary.dart';
import '../widgets/json_viewer.dart';

class CommandRegistersScreen extends StatefulWidget {
  const CommandRegistersScreen({super.key, required this.apiClient});

  final NorthboundApiClient apiClient;

  @override
  State<CommandRegistersScreen> createState() => _CommandRegistersScreenState();
}

class _CommandRegistersScreenState extends State<CommandRegistersScreen> {
  List<SourceSummary> sources = [];
  List<EmsCommandRegister> registers = [];
  String? selectedSourceId;
  EmsCommandRegister? selectedRegister;
  String search = '';
  String? error;
  bool loading = false;
  bool writing = false;
  Map<String, dynamic>? lastWrite;
  final valueController = TextEditingController(text: '0');
  final searchController = TextEditingController();

  @override
  void initState() {
    super.initState();
    refreshSources();
  }

  @override
  void dispose() {
    valueController.dispose();
    searchController.dispose();
    super.dispose();
  }

  Future<void> refreshSources() async {
    setState(() {
      loading = true;
      error = null;
    });
    final result = await widget.apiClient.getSourceSummary();
    if (!mounted) return;
    if (result.isSuccess) {
      sources = result.data ?? [];
      selectedSourceId = sources.isNotEmpty ? sources.first.sourceId : null;
      await refreshRegisters();
    } else {
      setState(() {
        loading = false;
        error = result.error;
      });
    }
  }

  Future<void> refreshRegisters() async {
    final sourceId = selectedSourceId;
    if (sourceId == null) {
      setState(() {
        registers = [];
        loading = false;
      });
      return;
    }
    setState(() {
      loading = true;
      error = null;
    });
    final result = await widget.apiClient.getEmsCommandRegisters(sourceId: sourceId);
    if (!mounted) return;
    setState(() {
      loading = false;
      if (result.isSuccess) {
        registers = result.data ?? [];
        selectedRegister = registers.isNotEmpty ? _preferredRegister(registers) : null;
      } else {
        error = result.error;
      }
    });
  }

  EmsCommandRegister _preferredRegister(List<EmsCommandRegister> items) {
    for (final address in const [164, 42, 44]) {
      for (final item in items) {
        if (item.address == address) return item;
      }
    }
    return items.first;
  }

  List<EmsCommandRegister> get filteredRegisters {
    final q = search.trim().toLowerCase();
    if (q.isEmpty) return registers;
    return registers.where((r) {
      final text = '${r.signalName} ${r.displayName} ${r.address} ${r.description} ${r.unit}'.toLowerCase();
      return text.contains(q);
    }).toList();
  }

  Future<void> writeSelected() async {
    final sourceId = selectedSourceId;
    final register = selectedRegister;
    final value = num.tryParse(valueController.text.trim());
    if (sourceId == null || register == null || value == null) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Write raw EMS register?'),
        content: Text('Source: $sourceId\nRegister: ${register.signalName} @ ${register.address}\nValue: $value\n\nUse this only for commissioning/debugging.'),
        actions: [
          TextButton(onPressed: () => Navigator.of(context).pop(false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.of(context).pop(true), child: const Text('Write')),
        ],
      ),
    );
    if (ok != true) return;

    setState(() {
      writing = true;
      error = null;
      lastWrite = null;
    });
    final result = await widget.apiClient.writeEmsRegister(
      sourceId: sourceId,
      signalName: register.signalName,
      value: value,
      readback: true,
      note: 'Flutter raw command register write',
    );
    if (!mounted) return;
    setState(() {
      writing = false;
      if (result.isSuccess) {
        lastWrite = result.data;
      } else {
        error = result.error;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final items = filteredRegisters;
    return Scaffold(
      appBar: AppBar(
        title: const Text('EMS Command Registers'),
        actions: [IconButton(onPressed: refreshRegisters, icon: const Icon(Icons.refresh))],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (loading) const LinearProgressIndicator(),
          if (error != null) Card(child: ListTile(leading: const Icon(Icons.error_outline), title: Text(error!))),
          _topPanel(),
          const SizedBox(height: 12),
          _writePanel(),
          const SizedBox(height: 12),
          Text('Writable registers (${items.length}/${registers.length})', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          for (final register in items) _registerTile(register),
          const SizedBox(height: 12),
          if (lastWrite != null) ExpansionTile(title: const Text('Last raw write result'), children: [JsonViewer(data: lastWrite!)]),
        ],
      ),
    );
  }

  Widget _topPanel() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Source and filter', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              value: selectedSourceId,
              decoration: const InputDecoration(labelText: 'Source'),
              items: [for (final source in sources) DropdownMenuItem(value: source.sourceId, child: Text('${source.displayName} • ${source.host}:${source.port}'))],
              onChanged: writing
                  ? null
                  : (value) {
                      setState(() => selectedSourceId = value);
                      refreshRegisters();
                    },
            ),
            const SizedBox(height: 12),
            TextField(
              controller: searchController,
              decoration: const InputDecoration(prefixIcon: Icon(Icons.search), labelText: 'Search register/address/name'),
              onChanged: (value) => setState(() => search = value),
            ),
          ],
        ),
      ),
    );
  }

  Widget _writePanel() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Raw write tool', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            const Text('Prefer the high-level Control Panel for normal operations. This raw writer is for commissioning.'),
            const SizedBox(height: 12),
            Wrap(
              spacing: 12,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                SizedBox(
                  width: 360,
                  child: DropdownButtonFormField<EmsCommandRegister>(
                    value: selectedRegister,
                    decoration: const InputDecoration(labelText: 'Register'),
                    items: [
                      for (final register in registers)
                        DropdownMenuItem(value: register, child: Text('${register.address} • ${register.signalName}', overflow: TextOverflow.ellipsis)),
                    ],
                    onChanged: writing ? null : (value) => setState(() => selectedRegister = value),
                  ),
                ),
                SizedBox(
                  width: 150,
                  child: TextField(
                    controller: valueController,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(labelText: 'Value'),
                  ),
                ),
                FilledButton.icon(
                  onPressed: writing ? null : writeSelected,
                  icon: const Icon(Icons.send),
                  label: Text(writing ? 'Writing...' : 'Write'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _registerTile(EmsCommandRegister register) {
    final selected = selectedRegister?.signalName == register.signalName && selectedRegister?.address == register.address;
    return Card(
      child: ListTile(
        selected: selected,
        leading: CircleAvatar(child: Text(register.address.toString(), style: const TextStyle(fontSize: 11))),
        title: Text(register.displayName),
        subtitle: Text('${register.signalName} • ${register.unit.isEmpty ? 'no unit' : register.unit}\n${register.description}'),
        isThreeLine: register.description.isNotEmpty,
        trailing: register.writable ? const Chip(label: Text('RW')) : const Chip(label: Text('RO')),
        onTap: () => setState(() => selectedRegister = register),
      ),
    );
  }
}
