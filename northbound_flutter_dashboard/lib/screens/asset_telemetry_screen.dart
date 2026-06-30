import 'package:flutter/material.dart';

import '../api/northbound_api_client.dart';
import '../models/asset_summary.dart';
import '../models/telemetry_signal.dart';
import '../widgets/json_viewer.dart';
import '../widgets/signal_tile.dart';

class AssetTelemetryScreen extends StatefulWidget {
  const AssetTelemetryScreen({super.key, required this.apiClient, required this.asset});

  final NorthboundApiClient apiClient;
  final AssetSummary asset;

  @override
  State<AssetTelemetryScreen> createState() => _AssetTelemetryScreenState();
}

class _AssetTelemetryScreenState extends State<AssetTelemetryScreen> {
  Map<String, dynamic>? raw;
  List<TelemetrySignal> signals = [];
  String? selectedCategory;
  String? error;
  bool loading = false;

  @override
  void initState() {
    super.initState();
    refresh();
  }

  Future<void> refresh() async {
    setState(() {
      loading = true;
      error = null;
    });
    final result = await widget.apiClient.getAssetTelemetry(widget.asset.assetId, category: selectedCategory);
    if (!mounted) return;
    setState(() {
      loading = false;
      if (result.isSuccess) {
        raw = result.data;
        final telemetry = result.data?['telemetry'] ?? result.data?['key_signals'];
        if (telemetry is Map) {
          signals = telemetry.entries
              .map((entry) => TelemetrySignal.fromEntry(entry.key.toString(), entry.value))
              .toList()
            ..sort((a, b) => a.category == b.category ? a.displayName.compareTo(b.displayName) : a.category.compareTo(b.category));
        } else {
          signals = [];
        }
      } else {
        error = result.error;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final categories = signals.map((s) => s.category).toSet().toList()..sort();
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.asset.displayName),
        actions: [IconButton(onPressed: refresh, icon: const Icon(Icons.refresh))],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (loading) const LinearProgressIndicator(),
          if (error != null) Card(child: ListTile(leading: const Icon(Icons.error), title: Text(error!))),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              ChoiceChip(
                label: const Text('All'),
                selected: selectedCategory == null,
                onSelected: (_) {
                  setState(() => selectedCategory = null);
                  refresh();
                },
              ),
              for (final c in categories)
                ChoiceChip(
                  label: Text(c),
                  selected: selectedCategory == c,
                  onSelected: (_) {
                    setState(() => selectedCategory = c);
                    refresh();
                  },
                ),
            ],
          ),
          const SizedBox(height: 12),
          Text('${signals.length} telemetry signals', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          for (final signal in signals) SignalTile(signal: signal),
          const SizedBox(height: 16),
          ExpansionTile(title: const Text('Raw asset payload'), children: [JsonViewer(data: raw ?? {})]),
        ],
      ),
    );
  }
}
