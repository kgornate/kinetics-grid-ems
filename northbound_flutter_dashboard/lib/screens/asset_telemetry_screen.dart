import 'package:flutter/material.dart';

import '../api/northbound_api_client.dart';
import '../models/asset_summary.dart';
import '../models/telemetry_signal.dart';
import '../utils/asset_field_strategy.dart';
import '../widgets/asset_group_section.dart';
import '../widgets/io_status_grid.dart';
import '../widgets/json_viewer.dart';
import '../widgets/metric_card.dart';
import '../widgets/operator_signal_table.dart';
import '../widgets/signal_metric_card.dart';

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
  String selectedView = 'operator';
  String search = '';
  String qualityFilter = 'all';
  bool faultAlarmOnly = false;
  String? error;
  bool loading = false;
  final searchController = TextEditingController();

  late final AssetUiProfile profile = AssetFieldStrategy.forAsset(widget.asset.assetId);

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
        final telemetry = result.data?['signals'] ?? result.data?['telemetry'] ?? result.data?['key_signals'];
        if (telemetry is Map) {
          signals = telemetry.entries
              .map((entry) => TelemetrySignal.fromEntry(entry.key.toString(), entry.value))
              .toList()
            ..sort((a, b) {
              final c = a.category.compareTo(b.category);
              if (c != 0) return c;
              final aa = a.address ?? 99999999;
              final bb = b.address ?? 99999999;
              if (aa != bb) return aa.compareTo(bb);
              return a.displayName.compareTo(b.displayName);
            });
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
    final allCategories = signals.map((s) => s.category).toSet().toList()..sort();
    final filtered = _filteredSignals();
    final primary = profile.primarySignals(signals).where(_signalMatchesActiveFiltersExceptSearch).toList();
    final grouped = profile.groupedSignals(filtered);
    final faultSignals = signals.where(_isFaultAlarmSignal).toList();
    final ioLikeSignals = widget.asset.assetId.contains('io') ? filtered : const <TelemetrySignal>[];

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
            if (primary.isNotEmpty) ...[
              _sectionHeader('Important operator values', '${primary.length} priority fields'),
              const SizedBox(height: 8),
              _signalCardGrid(primary.take(12).toList(), compact: true),
              const SizedBox(height: 12),
            ],
            if (faultSignals.isNotEmpty) ...[
              _faultAlarmPanel(faultSignals),
              const SizedBox(height: 12),
            ],
            _filterPanel(allCategories),
            const SizedBox(height: 12),
            Row(
              children: [
                Text('Asset Data', style: Theme.of(context).textTheme.headlineSmall),
                const SizedBox(width: 8),
                Chip(label: Text('${filtered.length}/${signals.length} shown')),
                const Spacer(),
                SegmentedButton<String>(
                  segments: const [
                    ButtonSegment(value: 'operator', label: Text('Operator'), icon: Icon(Icons.dashboard_customize)),
                    ButtonSegment(value: 'cards', label: Text('Cards'), icon: Icon(Icons.grid_view)),
                    ButtonSegment(value: 'table', label: Text('Table'), icon: Icon(Icons.table_rows)),
                  ],
                  selected: {selectedView},
                  onSelectionChanged: (v) => setState(() => selectedView = v.first),
                ),
              ],
            ),
            const SizedBox(height: 8),
            if (ioLikeSignals.isNotEmpty && selectedView == 'operator') ...[
              Text('Digital I/O style view', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 8),
              IoStatusGrid(signals: ioLikeSignals),
              const SizedBox(height: 12),
            ],
            if (selectedView == 'table')
              OperatorSignalTable(signals: filtered)
            else if (selectedView == 'cards')
              _signalCardGrid(filtered)
            else
              for (var i = 0; i < grouped.length; i++)
                AssetGroupSection(group: grouped[i], initiallyExpanded: i < 2),
            const SizedBox(height: 16),
            ExpansionTile(title: const Text('Raw asset payload'), children: [JsonViewer(data: raw ?? {})]),
          ],
        ),
      ),
    );
  }

  Widget _assetHero() {
    final color = widget.asset.online ? Colors.green : Colors.red;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(width: 8, color: color),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.all(18),
                child: Row(
                  children: [
                    CircleAvatar(
                      radius: 30,
                      backgroundColor: color.withOpacity(0.14),
                      foregroundColor: color,
                      child: Icon(profile.icon, size: 30),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(profile.title, style: Theme.of(context).textTheme.headlineSmall),
                          const SizedBox(height: 4),
                          SelectableText('${widget.asset.displayName} • ${widget.asset.assetId}'),
                          const SizedBox(height: 6),
                          Text(profile.operatorPurpose),
                        ],
                      ),
                    ),
                    Chip(label: Text(widget.asset.online ? 'ONLINE' : 'OFFLINE')),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _metricStrip() {
    final good = signals.where((s) => s.isGood).length;
    final bad = signals.length - good;
    final cats = signals.map((s) => s.category).toSet().length;
    final faults = signals.where(_isFaultAlarmSignal).length;
    final cards = [
      MetricCard(title: 'Configured Signals', value: widget.asset.signalCount.toString(), icon: Icons.sensors),
      MetricCard(title: 'Loaded Fields', value: signals.length.toString(), icon: Icons.list_alt),
      MetricCard(title: 'Categories', value: cats.toString(), icon: Icons.category),
      MetricCard(title: 'Good / Bad', value: '$good / $bad', icon: Icons.health_and_safety, good: bad == 0),
      MetricCard(title: 'Fault/Alarm Fields', value: faults.toString(), icon: Icons.warning_amber, good: faults == 0),
    ];
    return LayoutBuilder(
      builder: (context, constraints) {
        final crossAxisCount = constraints.maxWidth > 1250 ? 5 : constraints.maxWidth > 920 ? 3 : constraints.maxWidth > 620 ? 2 : 1;
        return GridView.count(
          crossAxisCount: crossAxisCount,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          childAspectRatio: constraints.maxWidth > 620 ? 3.1 : 4.5,
          children: cards,
        );
      },
    );
  }

  Widget _filterPanel(List<String> categories) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Field filters', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                ChoiceChip(label: const Text('All categories'), selected: selectedCategory == null, onSelected: (_) { setState(() => selectedCategory = null); refresh(); }),
                for (final c in categories)
                  ChoiceChip(label: Text(c), selected: selectedCategory == c, onSelected: (_) { setState(() => selectedCategory = c); refresh(); }),
              ],
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 12,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                SizedBox(
                  width: 240,
                  child: DropdownButtonFormField<String>(
                    value: qualityFilter,
                    decoration: const InputDecoration(labelText: 'Quality'),
                    items: const [
                      DropdownMenuItem(value: 'all', child: Text('All quality')),
                      DropdownMenuItem(value: 'good', child: Text('Good only')),
                      DropdownMenuItem(value: 'bad', child: Text('Bad / not-good only')),
                    ],
                    onChanged: (v) => setState(() => qualityFilter = v ?? 'all'),
                  ),
                ),
                FilterChip(label: const Text('Fault/alarm fields only'), selected: faultAlarmOnly, onSelected: (v) => setState(() => faultAlarmOnly = v)),
              ],
            ),
            const SizedBox(height: 10),
            TextField(
              controller: searchController,
              decoration: const InputDecoration(prefixIcon: Icon(Icons.search), labelText: 'Search field, value, category, quality, address, description'),
              onChanged: (value) => setState(() => search = value.trim().toLowerCase()),
            ),
          ],
        ),
      ),
    );
  }

  Widget _faultAlarmPanel(List<TelemetrySignal> faultSignals) {
    final active = faultSignals.where((s) => !s.isGood || _numericNonZero(s)).toList();
    return Card(
      child: ExpansionTile(
        initiallyExpanded: active.isNotEmpty,
        leading: Icon(active.isEmpty ? Icons.verified : Icons.warning_amber),
        title: Text(active.isEmpty ? 'Fault/alarm fields present, no obvious active issue' : 'Fault/alarm attention fields'),
        subtitle: Text('${faultSignals.length} fault/alarm-related fields, ${active.length} need attention'),
        childrenPadding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
        children: [
          _signalCardGrid((active.isEmpty ? faultSignals : active).take(8).toList(), compact: true),
        ],
      ),
    );
  }

  Widget _sectionHeader(String title, String subtitle) {
    return Row(
      children: [
        Text(title, style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(width: 8),
        Chip(label: Text(subtitle)),
      ],
    );
  }

  Widget _signalCardGrid(List<TelemetrySignal> data, {bool compact = false}) {
    if (data.isEmpty) {
      return const Card(child: ListTile(leading: Icon(Icons.search_off), title: Text('No matching fields')));
    }
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.maxWidth;
        final crossAxisCount = width > 1380 ? 4 : width > 1000 ? 3 : width > 680 ? 2 : 1;
        return GridView.count(
          crossAxisCount: crossAxisCount,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          childAspectRatio: compact ? 2.1 : 1.65,
          children: [for (final signal in data) SignalMetricCard(signal: signal, compact: compact)],
        );
      },
    );
  }

  List<TelemetrySignal> _filteredSignals() {
    return signals.where((signal) {
      if (!_signalMatchesActiveFiltersExceptSearch(signal)) return false;
      final s = search.trim().toLowerCase();
      if (s.isEmpty) return true;
      final text = '${signal.name} ${signal.displayName} ${signal.category} ${signal.valueText} ${signal.quality} ${signal.address} ${signal.description ?? ''}'.toLowerCase();
      return text.contains(s);
    }).toList();
  }

  bool _signalMatchesActiveFiltersExceptSearch(TelemetrySignal signal) {
    if (selectedCategory != null && signal.category != selectedCategory) return false;
    if (qualityFilter == 'good' && !signal.isGood) return false;
    if (qualityFilter == 'bad' && signal.isGood) return false;
    if (faultAlarmOnly && !_isFaultAlarmSignal(signal)) return false;
    return true;
  }

  bool _isFaultAlarmSignal(TelemetrySignal signal) {
    final text = '${signal.name} ${signal.displayName} ${signal.category} ${signal.description ?? ''}'.toLowerCase();
    return text.contains('fault') || text.contains('alarm') || text.contains('warning') || text.contains('emergency') || signal.category.toLowerCase().contains('fault');
  }

  bool _numericNonZero(TelemetrySignal signal) {
    final v = signal.value;
    if (v is num) return v != 0;
    return false;
  }
}
