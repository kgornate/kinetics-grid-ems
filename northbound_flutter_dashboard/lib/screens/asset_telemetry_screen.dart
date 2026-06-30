import 'package:flutter/material.dart';

import '../api/northbound_api_client.dart';
import '../models/asset_summary.dart';
import '../models/telemetry_signal.dart';
import '../widgets/json_viewer.dart';
import '../widgets/metric_card.dart';
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
  String search = '';
  String? error;
  bool loading = false;
  final searchController = TextEditingController();

  @override
  void initState() {
    super.initState();
    refresh();
  }

  @override
  void dispose() {
    searchController.dispose();
    super.dispose();
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
        final telemetry = result.data?['telemetry'] ?? result.data?['signals'] ?? result.data?['key_signals'];
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
    final filtered = _filteredSignals();
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.asset.displayName),
        actions: [IconButton(onPressed: refresh, icon: const Icon(Icons.refresh))],
      ),
      body: RefreshIndicator(
        onRefresh: refresh,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _assetHero(),
            const SizedBox(height: 12),
            _metricStrip(),
            const SizedBox(height: 12),
            if (loading) const LinearProgressIndicator(),
            if (error != null) Card(child: ListTile(leading: const Icon(Icons.error), title: Text(error!))),
            _filterPanel(categories),
            const SizedBox(height: 12),
            Row(
              children: [
                Text('Telemetry Signals', style: Theme.of(context).textTheme.headlineSmall),
                const SizedBox(width: 8),
                Chip(label: Text('${filtered.length}/${signals.length} shown')),
              ],
            ),
            const SizedBox(height: 8),
            if (filtered.isEmpty)
              const Card(child: ListTile(leading: Icon(Icons.search_off), title: Text('No matching signals')))
            else
              for (final signal in filtered) SignalTile(signal: signal),
            const SizedBox(height: 16),
            ExpansionTile(title: const Text('Raw asset payload'), children: [JsonViewer(data: raw ?? {})]),
          ],
        ),
      ),
    );
  }

  Widget _assetHero() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Row(
          children: [
            CircleAvatar(
              radius: 28,
              backgroundColor: widget.asset.online ? Colors.green.withOpacity(0.14) : Colors.red.withOpacity(0.14),
              foregroundColor: widget.asset.online ? Colors.green : Colors.red,
              child: Icon(widget.asset.online ? Icons.check_circle : Icons.cancel, size: 30),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(widget.asset.displayName, style: Theme.of(context).textTheme.headlineSmall),
                  const SizedBox(height: 4),
                  SelectableText(widget.asset.assetId),
                  if (widget.asset.description != null) Text(widget.asset.description!),
                ],
              ),
            ),
            Chip(label: Text(widget.asset.online ? 'ONLINE' : 'OFFLINE')),
          ],
        ),
      ),
    );
  }

  Widget _metricStrip() {
    final good = signals.where((s) => s.quality.toLowerCase() == 'good').length;
    final bad = signals.where((s) => s.quality.toLowerCase() != 'good').length;
    final categories = signals.map((s) => s.category).toSet().length;
    return LayoutBuilder(
      builder: (context, constraints) {
        final cards = [
          MetricCard(title: 'Configured Signals', value: widget.asset.signalCount.toString(), icon: Icons.sensors),
          MetricCard(title: 'Loaded Signals', value: signals.length.toString(), icon: Icons.list_alt),
          MetricCard(title: 'Good Quality', value: good.toString(), icon: Icons.check_circle, good: bad == 0),
          MetricCard(title: 'Categories', value: categories.toString(), icon: Icons.category),
        ];
        final crossAxisCount = constraints.maxWidth > 1100 ? 4 : constraints.maxWidth > 760 ? 2 : 1;
        return GridView.count(
          crossAxisCount: crossAxisCount,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          childAspectRatio: constraints.maxWidth > 760 ? 3.1 : 4.5,
          children: cards,
        );
      },
    );
  }

  Widget _filterPanel(List<String> categories) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
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
            const SizedBox(height: 10),
            TextField(
              controller: searchController,
              decoration: const InputDecoration(prefixIcon: Icon(Icons.search), labelText: 'Search signal name, display name, category, or value'),
              onChanged: (value) => setState(() => search = value.trim().toLowerCase()),
            ),
          ],
        ),
      ),
    );
  }

  List<TelemetrySignal> _filteredSignals() {
    if (search.isEmpty) return signals;
    return signals.where((signal) {
      final text = '${signal.name} ${signal.displayName} ${signal.category} ${signal.valueText} ${signal.quality}'.toLowerCase();
      return text.contains(search);
    }).toList();
  }
}
