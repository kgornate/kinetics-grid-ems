import 'dart:convert';

import 'package:flutter/material.dart';

import '../core/state/gateway_controller.dart';
import '../models/gateway_models.dart';
import '../widgets/common_widgets.dart';

class HistorianScreen extends StatefulWidget {
  const HistorianScreen({super.key, required this.controller});

  final GatewayController controller;

  @override
  State<HistorianScreen> createState() => _HistorianScreenState();
}

class _HistorianScreenState extends State<HistorianScreen> {
  String? _assetId;
  bool _loading = false;
  List<Map<String, dynamic>> _samples = <Map<String, dynamic>>[];

  Future<void> _load() async {
    final assetId = _assetId;
    if (assetId == null) return;
    setState(() => _loading = true);
    try {
      _samples = await widget.controller.loadHistorian(assetId, limit: 200);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final assets = widget.controller.plant.assets.keys.toList()..sort();
    _assetId ??= assets.isEmpty ? null : assets.first;
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        children: [
          SectionHeader(
            'Historian',
            subtitle: 'Compressed SQLite telemetry samples stored by the gateway.',
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: DropdownButtonFormField<String>(
                  value: _assetId,
                  decoration: const InputDecoration(labelText: 'Asset', border: OutlineInputBorder()),
                  items: assets
                      .map((asset) => DropdownMenuItem(value: asset, child: Text(prettifyKey(asset))))
                      .toList(),
                  onChanged: (value) => setState(() => _assetId = value),
                ),
              ),
              const SizedBox(width: 12),
              FilledButton.icon(
                onPressed: _loading ? null : _load,
                icon: const Icon(Icons.query_stats),
                label: const Text('Load samples'),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _samples.isEmpty
                    ? const Center(child: Text('Select an asset and load its recent samples.'))
                    : Card(
                        child: ListView.separated(
                          itemCount: _samples.length,
                          separatorBuilder: (_, __) => const Divider(height: 1),
                          itemBuilder: (context, index) {
                            final sample = _samples[index];
                            final timestamp = sample['timestamp'] ?? sample['created_at'] ?? '--';
                            return ListTile(
                              leading: const Icon(Icons.timeline),
                              title: Text(timestamp.toString()),
                              subtitle: Text('Sample ${index + 1}'),
                              onTap: () => _showSample(context, sample),
                            );
                          },
                        ),
                      ),
          ),
        ],
      ),
    );
  }

  void _showSample(BuildContext context, Map<String, dynamic> sample) {
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Historian sample'),
        content: SizedBox(
          width: 760,
          child: SingleChildScrollView(
            child: SelectableText(const JsonEncoder.withIndent('  ').convert(sample)),
          ),
        ),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
      ),
    );
  }
}
