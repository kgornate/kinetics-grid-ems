import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/northbound_api_client.dart';
import '../models/asset_summary.dart';
import '../models/log_filter_options.dart';
import '../models/log_record.dart';
import '../models/history_snapshot_record.dart';
import '../models/point_history_record.dart';
import '../models/telemetry_signal.dart';
import '../utils/asset_field_strategy.dart';
import '../utils/value_formatters.dart';
import '../widgets/empty_state.dart';
import '../widgets/json_viewer.dart';
import '../widgets/metric_card.dart';
import '../widgets/operator_signal_table.dart';
import '../widgets/signal_metric_card.dart';

class LogsScreen extends StatefulWidget {
  const LogsScreen({super.key, required this.apiClient});

  final NorthboundApiClient apiClient;

  @override
  State<LogsScreen> createState() => _LogsScreenState();
}

class _LogsScreenState extends State<LogsScreen> with SingleTickerProviderStateMixin {
  late final TabController tabController;

  List<AssetSummary> assets = [];
  AssetSummary? selectedAsset;
  Map<String, dynamic>? selectedAssetRaw;
  List<TelemetrySignal> assetSignals = [];
  List<TelemetrySignal> filteredSignals = [];
  String? selectedCategory;
  String assetSearch = '';
  String qualityFilter = 'all';
  bool faultAlarmOnly = false;

  String? selectedHistorySignal; // retained for backwards compatibility with older point-history flow
  final Set<String> selectedHistorySignals = <String>{};
  List<PointHistoryRecord> pointRows = [];
  List<HistorySnapshotRecord> snapshotRows = [];
  int historyLimit = 100;
  String? historyCategory;
  String historySearch = '';
  String historyQualityFilter = 'all';
  bool historyFaultAlarmOnly = false;

  LogFilterOptions options = const LogFilterOptions();
  LogQuery query = const LogQuery(limit: 100);
  LogQueryResult? result;
  Map<String, dynamic>? summary;
  bool showApiAccessEvents = false;

  String? error;
  bool loading = false;

  final assetSearchController = TextEditingController();
  final eventSearchController = TextEditingController();
  final historySearchController = TextEditingController();
  final fromController = TextEditingController();
  final toController = TextEditingController();

  @override
  void initState() {
    super.initState();
    tabController = TabController(length: 3, vsync: this);
    refreshAll();
  }

  @override
  void dispose() {
    tabController.dispose();
    assetSearchController.dispose();
    eventSearchController.dispose();
    historySearchController.dispose();
    fromController.dispose();
    toController.dispose();
    super.dispose();
  }

  Future<void> refreshAll() async {
    setState(() {
      loading = true;
      error = null;
    });

    final assetResult = await widget.apiClient.getAssets();
    final filterResult = await widget.apiClient.getLogFilterOptions();
    final summaryResult = await widget.apiClient.getLogSummary(fromTime: _emptyToNull(fromController.text), toTime: _emptyToNull(toController.text));
    final logsResult = await widget.apiClient.getLogs(_queryFromUi());

    if (!mounted) return;
    setState(() {
      loading = false;
      if (assetResult.isSuccess) {
        assets = assetResult.data ?? [];
        selectedAsset ??= assets.isNotEmpty ? assets.first : null;
      }
      if (filterResult.isSuccess) options = filterResult.data ?? const LogFilterOptions();
      if (summaryResult.isSuccess) summary = summaryResult.data;
      if (logsResult.isSuccess) result = logsResult.data;
      error = assetResult.error ?? filterResult.error ?? summaryResult.error ?? logsResult.error;
    });

    if (selectedAsset != null) await loadAssetData(selectedAsset!.assetId);
  }

  Future<void> loadAssetData(String assetId) async {
    final matches = assets.where((a) => a.assetId == assetId);
    final asset = matches.isEmpty ? selectedAsset : matches.first;
    setState(() {
      loading = true;
      error = null;
      selectedAsset = asset;
    });
    final result = await widget.apiClient.getAssetTelemetry(assetId, category: selectedCategory);
    if (!mounted) return;
    setState(() {
      loading = false;
      if (result.isSuccess) {
        selectedAssetRaw = result.data;
        final telemetry = result.data?['signals'] ?? result.data?['telemetry'] ?? result.data?['key_signals'];
        if (telemetry is Map) {
          assetSignals = telemetry.entries
              .map((entry) => TelemetrySignal.fromEntry(entry.key.toString(), entry.value))
              .toList()
            ..sort(_signalSort);
          _applyAssetFilters(updateState: false);
          if (assetSignals.isEmpty) {
            selectedHistorySignal = null;
            selectedHistorySignals.clear();
            snapshotRows = [];
          } else {
            final profile = AssetFieldStrategy.forAsset(assetId);
            if (selectedHistorySignal == null || !assetSignals.any((s) => s.name == selectedHistorySignal)) {
              selectedHistorySignal = profile.primarySignals(assetSignals, maxCount: 1).first.name;
            }
            selectedHistorySignals.removeWhere((name) => !assetSignals.any((s) => s.name == name));
            if (selectedHistorySignals.isEmpty) {
              selectedHistorySignals.addAll(profile.primarySignals(assetSignals, maxCount: 8).map((s) => s.name));
            }
          }
        } else {
          assetSignals = [];
          filteredSignals = [];
        }
      } else {
        error = result.error;
      }
    });
  }

  Future<void> loadPointHistory() async {
    // Backward-compatible single-point historian loader. The v0.7 operator
    // historian uses snapshot rows for a multi-column table, but keeping this
    // method is useful if older gateway builds only expose /api/storage/points.
    final assetId = selectedAsset?.assetId;
    final signalName = selectedHistorySignal;
    if (assetId == null || signalName == null || signalName.isEmpty) return;
    setState(() {
      loading = true;
      error = null;
    });
    final result = await widget.apiClient.getPoints(assetId: assetId, signalName: signalName, limit: historyLimit);
    if (!mounted) return;
    setState(() {
      loading = false;
      if (result.isSuccess) {
        final rawItems = result.data?['items'];
        pointRows = rawItems is List
            ? rawItems.whereType<Map>().map((item) => PointHistoryRecord.fromJson(Map<String, dynamic>.from(item))).toList()
            : const [];
      } else {
        error = result.error;
      }
    });
  }

  Future<void> loadHistorySnapshots() async {
    final assetId = selectedAsset?.assetId;
    if (assetId == null || assetId.isEmpty) return;
    setState(() {
      loading = true;
      error = null;
    });
    final result = await widget.apiClient.getSnapshots(assetId: assetId, limit: historyLimit);
    if (!mounted) return;
    setState(() {
      loading = false;
      if (result.isSuccess) {
        final rawItems = result.data?['items'];
        snapshotRows = rawItems is List
            ? rawItems.whereType<Map>().map((item) => HistorySnapshotRecord.fromJson(Map<String, dynamic>.from(item))).toList()
            : const [];
        pointRows = [];
      } else {
        error = result.error;
      }
    });
  }

  Future<void> refreshEvents() async {
    setState(() {
      loading = true;
      error = null;
      query = _queryFromUi(offset: 0);
    });
    final summaryResult = await widget.apiClient.getLogSummary(fromTime: _emptyToNull(fromController.text), toTime: _emptyToNull(toController.text));
    final logsResult = await widget.apiClient.getLogs(query);
    if (!mounted) return;
    setState(() {
      loading = false;
      if (summaryResult.isSuccess) summary = summaryResult.data;
      if (logsResult.isSuccess) result = logsResult.data;
      error = summaryResult.error ?? logsResult.error;
    });
  }

  LogQuery _queryFromUi({int? offset}) {
    return query.copyWith(
      fromTime: _emptyToNull(fromController.text),
      toTime: _emptyToNull(toController.text),
      search: _emptyToNull(eventSearchController.text),
      offset: offset ?? query.offset,
      clearFromTime: _emptyToNull(fromController.text) == null,
      clearToTime: _emptyToNull(toController.text) == null,
      clearSearch: _emptyToNull(eventSearchController.text) == null,
    );
  }

  void _applyAssetFilters({bool updateState = true}) {
    final textSearch = assetSearch.trim().toLowerCase();
    final next = assetSignals.where((signal) {
      if (selectedCategory != null && signal.category != selectedCategory) return false;
      if (qualityFilter == 'good' && !signal.isGood) return false;
      if (qualityFilter == 'bad' && signal.isGood) return false;
      if (faultAlarmOnly && !_isFaultAlarmSignal(signal)) return false;
      final text = '${signal.name} ${signal.displayName} ${signal.category} ${signal.valueText} ${signal.quality} ${signal.address} ${signal.description ?? ''}'.toLowerCase();
      return textSearch.isEmpty || text.contains(textSearch);
    }).toList();
    if (updateState) {
      setState(() => filteredSignals = next);
    } else {
      filteredSignals = next;
    }
  }

  void _clearEvents() {
    eventSearchController.clear();
    fromController.clear();
    toController.clear();
    setState(() {
      query = const LogQuery(limit: 100);
      showApiAccessEvents = false;
    });
    refreshEvents();
  }

  Future<void> _showExportUrl() async {
    final url = widget.apiClient.logExportUrl(_queryFromUi(offset: 0));
    await Clipboard.setData(ClipboardData(text: url));
    if (!mounted) return;
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Gateway-event CSV export URL copied'),
        content: SelectableText(url),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Asset Data & Logs'),
        bottom: TabBar(
          controller: tabController,
          tabs: const [
            Tab(icon: Icon(Icons.table_chart), text: 'Live Asset Fields'),
            Tab(icon: Icon(Icons.history), text: 'Historian'),
            Tab(icon: Icon(Icons.event_note), text: 'Gateway Events'),
          ],
        ),
        actions: [
          IconButton(tooltip: 'Copy gateway-event CSV export URL', onPressed: _showExportUrl, icon: const Icon(Icons.download)),
          IconButton(tooltip: 'Refresh', onPressed: refreshAll, icon: const Icon(Icons.refresh)),
        ],
      ),
      body: Column(
        children: [
          if (loading) const LinearProgressIndicator(),
          if (error != null) Padding(padding: const EdgeInsets.all(12), child: Card(child: ListTile(leading: const Icon(Icons.error), title: Text(error!)))),
          Expanded(
            child: TabBarView(
              controller: tabController,
              children: [_assetFieldsTab(), _historyTab(), _gatewayEventsTab()],
            ),
          ),
        ],
      ),
    );
  }

  Widget _assetFieldsTab() {
    final categories = assetSignals.map((s) => s.category).toSet().toList()..sort();
    final profile = AssetFieldStrategy.forAsset(selectedAsset?.assetId ?? '');
    final primary = profile.primarySignals(assetSignals).where((s) => filteredSignals.any((f) => f.name == s.name)).toList();
    return RefreshIndicator(
      onRefresh: () async => loadAssetData(selectedAsset?.assetId ?? ''),
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _operatorIntentBanner(),
          const SizedBox(height: 12),
          _assetSelectorCard(),
          const SizedBox(height: 12),
          _assetPurposeCard(profile),
          const SizedBox(height: 12),
          _assetSummaryMetrics(profile),
          const SizedBox(height: 12),
          if (primary.isNotEmpty) ...[
            _sectionHeader('Important values for selected asset', '${primary.length} priority fields'),
            const SizedBox(height: 8),
            _signalCardGrid(primary.take(12).toList(), compact: true),
            const SizedBox(height: 12),
          ],
          _assetFieldFilters(categories),
          const SizedBox(height: 12),
          Row(
            children: [
              Text('Operator field table', style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(width: 8),
              Chip(label: Text('${filteredSignals.length}/${assetSignals.length} fields')),
            ],
          ),
          const SizedBox(height: 8),
          OperatorSignalTable(
            signals: filteredSignals,
            onSelect: (signal) {
              setState(() {
                selectedHistorySignal = signal.name;
                selectedHistorySignals
                  ..clear()
                  ..add(signal.name);
              });
              tabController.animateTo(1);
              loadHistorySnapshots();
            },
          ),
          const SizedBox(height: 12),
          _assetGroupedPreview(profile),
          const SizedBox(height: 12),
          ExpansionTile(title: const Text('Raw selected asset payload'), children: [JsonViewer(data: selectedAssetRaw ?? {})]),
        ],
      ),
    );
  }

  Widget _historyTab() {
    return RefreshIndicator(
      onRefresh: loadHistorySnapshots,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _operatorIntentBanner(history: true),
          const SizedBox(height: 12),
          _historyFilterCard(),
          const SizedBox(height: 12),
          _historySummaryCards(),
          const SizedBox(height: 12),
          Row(
            children: [
              Text('Historical snapshot table', style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(width: 8),
              Chip(label: Text('${snapshotRows.length} rows')),
              Chip(label: Text('${_historyVisibleColumns().length} columns')),
            ],
          ),
          const SizedBox(height: 8),
          _historyWideTable(),
        ],
      ),
    );
  }

  Widget _gatewayEventsTab() {
    final rawItems = result?.items ?? const <LogRecord>[];
    final shown = showApiAccessEvents ? rawItems : rawItems.where((r) => r.eventType != 'api_access' && r.source != 'api').toList();
    return RefreshIndicator(
      onRefresh: refreshEvents,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _gatewayEventsNotice(),
          const SizedBox(height: 12),
          _eventSummaryCards(shown.length),
          const SizedBox(height: 12),
          _eventFiltersCard(),
          const SizedBox(height: 12),
          Row(
            children: [
              Text('Gateway technical events', style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(width: 8),
              Chip(label: Text('${result?.total ?? 0} total')),
              Chip(label: Text('${shown.length} shown')),
            ],
          ),
          const SizedBox(height: 8),
          if (shown.isEmpty)
            const EmptyState(title: 'No operator-relevant gateway events', subtitle: 'API access logs are hidden by default. Enable them in the filters if needed.')
          else
            for (final item in shown) _LogTile(record: item),
          const SizedBox(height: 12),
          _paginationControls(),
        ],
      ),
    );
  }

  Widget _operatorIntentBanner({bool history = false}) {
    return Card(
      child: ListTile(
        leading: Icon(history ? Icons.history : Icons.table_chart),
        title: Text(history ? 'Historical telemetry values' : 'Operator asset data, not API access logs'),
        subtitle: Text(history
            ? 'This tab reads stored telemetry snapshots from SQLite and renders them as a row/column table. Choose asset fields as columns, then load rows.'
            : 'This tab shows the decoded NorthBound fields for each real asset. Use asset/category/quality/search filters to inspect BMS, PCS, meter, fire, cooling, I/O and remote-status data.'),
      ),
    );
  }

  Widget _assetPurposeCard(AssetUiProfile profile) {
    return Card(
      child: ListTile(
        leading: CircleAvatar(child: Icon(profile.icon)),
        title: Text(profile.title),
        subtitle: Text(profile.operatorPurpose),
      ),
    );
  }

  Widget _gatewayEventsNotice() {
    return Card(
      child: ListTile(
        leading: const Icon(Icons.info_outline),
        title: const Text('Gateway Events are maintenance/developer audit logs'),
        subtitle: const Text('The main operator logs are Live Asset Fields and Historian. API access events are hidden by default because they mostly show dashboard polling calls like GET /api/assets.'),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('Show API access'),
            Switch(value: showApiAccessEvents, onChanged: (v) => setState(() => showApiAccessEvents = v)),
          ],
        ),
      ),
    );
  }

  Widget _assetSelectorCard() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Wrap(
          spacing: 12,
          runSpacing: 12,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            SizedBox(
              width: 360,
              child: DropdownButtonFormField<String>(
                value: selectedAsset?.assetId,
                decoration: const InputDecoration(labelText: 'Asset'),
                items: [for (final asset in assets) DropdownMenuItem(value: asset.assetId, child: Text('${asset.displayName} (${asset.assetId})', overflow: TextOverflow.ellipsis))],
                onChanged: (v) {
                  if (v == null) return;
                  selectedCategory = null;
                  selectedHistorySignal = null;
                  loadAssetData(v);
                },
              ),
            ),
            FilledButton.icon(onPressed: selectedAsset == null ? null : () => loadAssetData(selectedAsset!.assetId), icon: const Icon(Icons.refresh), label: const Text('Load asset fields')),
          ],
        ),
      ),
    );
  }

  Widget _assetSummaryMetrics(AssetUiProfile profile) {
    final good = assetSignals.where((s) => s.isGood).length;
    final bad = assetSignals.length - good;
    final cats = assetSignals.map((s) => s.category).toSet().length;
    final faults = assetSignals.where(_isFaultAlarmSignal).length;
    final cards = [
      MetricCard(title: 'Selected Asset', value: selectedAsset?.displayName ?? '-', subtitle: selectedAsset?.assetId, icon: profile.icon),
      MetricCard(title: 'Loaded Fields', value: assetSignals.length.toString(), icon: Icons.list_alt),
      MetricCard(title: 'Categories', value: cats.toString(), icon: Icons.category),
      MetricCard(title: 'Good / Bad', value: '$good / $bad', icon: Icons.health_and_safety, good: bad == 0),
      MetricCard(title: 'Fault/Alarm Fields', value: faults.toString(), icon: Icons.warning_amber, good: faults == 0),
    ];
    return _metricGrid(cards);
  }

  Widget _assetFieldFilters(List<String> categories) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Asset field filters', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                ChoiceChip(label: const Text('All categories'), selected: selectedCategory == null, onSelected: (_) { selectedCategory = null; loadAssetData(selectedAsset?.assetId ?? ''); }),
                for (final c in categories) ChoiceChip(label: Text(c), selected: selectedCategory == c, onSelected: (_) { selectedCategory = c; loadAssetData(selectedAsset?.assetId ?? ''); }),
              ],
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 12,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                SizedBox(
                  width: 230,
                  child: DropdownButtonFormField<String>(
                    value: qualityFilter,
                    decoration: const InputDecoration(labelText: 'Quality'),
                    items: const [
                      DropdownMenuItem(value: 'all', child: Text('All quality')),
                      DropdownMenuItem(value: 'good', child: Text('Good only')),
                      DropdownMenuItem(value: 'bad', child: Text('Bad / not-good only')),
                    ],
                    onChanged: (v) {
                      qualityFilter = v ?? 'all';
                      _applyAssetFilters();
                    },
                  ),
                ),
                FilterChip(label: const Text('Fault/alarm fields only'), selected: faultAlarmOnly, onSelected: (v) { faultAlarmOnly = v; _applyAssetFilters(); }),
              ],
            ),
            const SizedBox(height: 10),
            TextField(
              controller: assetSearchController,
              decoration: const InputDecoration(prefixIcon: Icon(Icons.search), labelText: 'Search field, value, unit, category, quality, address, description'),
              onChanged: (value) {
                assetSearch = value;
                _applyAssetFilters();
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _assetGroupedPreview(AssetUiProfile profile) {
    final groups = profile.groupedSignals(assetSignals);
    if (groups.isEmpty) return const SizedBox.shrink();
    return Card(
      child: ExpansionTile(
        leading: const Icon(Icons.view_module),
        title: const Text('Asset data grouping strategy'),
        subtitle: const Text('How this asset is organized for operator and engineering inspection.'),
        childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        children: [
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final group in groups)
                Chip(avatar: Icon(group.icon, size: 18), label: Text('${group.label}: ${group.signals.length}')),
            ],
          ),
        ],
      ),
    );
  }

  List<TelemetrySignal> _historyAvailableSignals() {
    final textSearch = historySearch.trim().toLowerCase();
    return assetSignals.where((signal) {
      if (historyCategory != null && signal.category != historyCategory) return false;
      if (historyQualityFilter == 'good' && !signal.isGood) return false;
      if (historyQualityFilter == 'bad' && signal.isGood) return false;
      if (historyFaultAlarmOnly && !_isFaultAlarmSignal(signal)) return false;
      final text = '${signal.name} ${signal.displayName} ${signal.category} ${signal.valueText} ${signal.quality} ${signal.address} ${signal.description ?? ''}'.toLowerCase();
      return textSearch.isEmpty || text.contains(textSearch);
    }).toList()..sort(_signalSort);
  }

  List<TelemetrySignal> _historyVisibleColumns() {
    final available = _historyAvailableSignals();
    return available.where((s) => selectedHistorySignals.contains(s.name)).toList();
  }

  void _selectAllVisibleHistoryColumns() {
    setState(() {
      selectedHistorySignals
        ..clear()
        ..addAll(_historyAvailableSignals().map((s) => s.name));
    });
  }

  void _selectPriorityHistoryColumns() {
    final profile = AssetFieldStrategy.forAsset(selectedAsset?.assetId ?? '');
    setState(() {
      selectedHistorySignals
        ..clear()
        ..addAll(profile.primarySignals(assetSignals, maxCount: 8).map((s) => s.name));
    });
  }

  Widget _historyFilterCard() {
    final categories = assetSignals.map((s) => s.category).toSet().toList()..sort();
    final availableSignals = _historyAvailableSignals();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Historian filters and columns', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 6),
            Text(
              'The historian is now a row/column table. Choose an asset, filter its live field list by category/search/quality, then select which fields become table columns.',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 14),
            Wrap(
              spacing: 12,
              runSpacing: 12,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                SizedBox(
                  width: 340,
                  child: DropdownButtonFormField<String>(
                    value: selectedAsset?.assetId,
                    decoration: const InputDecoration(labelText: 'Asset'),
                    items: [for (final asset in assets) DropdownMenuItem(value: asset.assetId, child: Text('${asset.displayName} (${asset.assetId})', overflow: TextOverflow.ellipsis))],
                    onChanged: (v) async {
                      if (v == null) return;
                      historyCategory = null;
                      historySearch = '';
                      historySearchController.clear();
                      selectedCategory = null;
                      selectedHistorySignal = null;
                      selectedHistorySignals.clear();
                      snapshotRows = [];
                      await loadAssetData(v);
                    },
                  ),
                ),
                SizedBox(
                  width: 190,
                  child: DropdownButtonFormField<String>(
                    value: historyCategory ?? 'all',
                    decoration: const InputDecoration(labelText: 'Category'),
                    items: [
                      const DropdownMenuItem(value: 'all', child: Text('All categories')),
                      for (final c in categories) DropdownMenuItem(value: c, child: Text(c, overflow: TextOverflow.ellipsis)),
                    ],
                    onChanged: (v) => setState(() => historyCategory = v == null || v == 'all' ? null : v),
                  ),
                ),
                SizedBox(
                  width: 170,
                  child: DropdownButtonFormField<String>(
                    value: historyQualityFilter,
                    decoration: const InputDecoration(labelText: 'Quality'),
                    items: const [
                      DropdownMenuItem(value: 'all', child: Text('All quality')),
                      DropdownMenuItem(value: 'good', child: Text('Good only')),
                      DropdownMenuItem(value: 'bad', child: Text('Bad only')),
                    ],
                    onChanged: (v) => setState(() => historyQualityFilter = v ?? 'all'),
                  ),
                ),
                SizedBox(
                  width: 150,
                  child: DropdownButtonFormField<int>(
                    value: historyLimit,
                    decoration: const InputDecoration(labelText: 'Rows'),
                    items: const [50, 100, 200, 500, 1000].map((v) => DropdownMenuItem(value: v, child: Text('$v'))).toList(),
                    onChanged: (v) => setState(() => historyLimit = v ?? 100),
                  ),
                ),
                FilterChip(label: const Text('Fault/alarm fields'), selected: historyFaultAlarmOnly, onSelected: (v) => setState(() => historyFaultAlarmOnly = v)),
                FilledButton.icon(onPressed: loadHistorySnapshots, icon: const Icon(Icons.table_rows), label: const Text('Load historian table')),
              ],
            ),
            const SizedBox(height: 12),
            TextField(
              controller: historySearchController,
              decoration: const InputDecoration(prefixIcon: Icon(Icons.search), labelText: 'Search fields to use as historian columns'),
              onChanged: (value) => setState(() => historySearch = value),
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                OutlinedButton.icon(onPressed: _selectPriorityHistoryColumns, icon: const Icon(Icons.star_outline), label: const Text('Priority columns')),
                OutlinedButton.icon(onPressed: _selectAllVisibleHistoryColumns, icon: const Icon(Icons.done_all), label: const Text('Select all visible')),
                OutlinedButton.icon(onPressed: () => setState(() => selectedHistorySignals.clear()), icon: const Icon(Icons.clear), label: const Text('Clear columns')),
                Chip(label: Text('${availableSignals.length} matching fields')),
                Chip(label: Text('${selectedHistorySignals.length} selected')),
              ],
            ),
            const SizedBox(height: 10),
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 170),
              child: SingleChildScrollView(
                child: Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final signal in availableSignals)
                      FilterChip(
                        label: Text(signal.displayName, overflow: TextOverflow.ellipsis),
                        selected: selectedHistorySignals.contains(signal.name),
                        onSelected: (selected) => setState(() {
                          if (selected) {
                            selectedHistorySignals.add(signal.name);
                          } else {
                            selectedHistorySignals.remove(signal.name);
                          }
                        }),
                      ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _historySummaryCards() {
    final availableSignals = _historyAvailableSignals();
    final columns = _historyVisibleColumns();
    final storedSignals = snapshotRows.expand((row) => row.signals.keys).toSet().length;
    final cards = [
      MetricCard(title: 'Selected Asset', value: selectedAsset?.displayName ?? '-', subtitle: selectedAsset?.assetId, icon: Icons.hub),
      MetricCard(title: 'Live Fields Available', value: assetSignals.length.toString(), subtitle: '${availableSignals.length} after filters', icon: Icons.view_column),
      MetricCard(title: 'Table Columns', value: columns.length.toString(), subtitle: columns.isEmpty ? 'none selected' : 'selected fields', icon: Icons.table_chart),
      MetricCard(title: 'Rows Loaded', value: snapshotRows.length.toString(), subtitle: '$historyLimit requested', icon: Icons.table_rows),
      MetricCard(title: 'Stored Fields Found', value: storedSignals.toString(), subtitle: 'from snapshot rows', icon: Icons.history),
    ];
    return _metricGrid(cards);
  }

  Widget _historyWideTable() {
    final columns = _historyVisibleColumns();
    if (selectedAsset == null) {
      return const EmptyState(title: 'Select an asset', subtitle: 'Choose an asset to load its field list and historian rows.');
    }
    if (columns.isEmpty) {
      return const EmptyState(title: 'No historian columns selected', subtitle: 'Use category/search filters, then select fields to show as table columns.');
    }
    if (snapshotRows.isEmpty) {
      return const EmptyState(
        title: 'No history rows loaded',
        subtitle: 'Click Load historian table. If rows remain empty, the gateway may not have written snapshots yet or storage may only start after the snapshot interval.',
      );
    }

    return Card(
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: DataTable(
          headingRowHeight: 64,
          dataRowMinHeight: 46,
          dataRowMaxHeight: 58,
          columns: [
            const DataColumn(label: Text('Timestamp UTC')),
            for (final signal in columns)
              DataColumn(
                label: SizedBox(
                  width: 170,
                  child: Text(
                    signal.displayName,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ),
          ],
          rows: [
            for (final row in snapshotRows)
              DataRow(cells: [
                DataCell(Text(ValueFormatters.compactDateTime(row.timestampUtc))),
                for (final signal in columns)
                  DataCell(
                    SizedBox(
                      width: 170,
                      child: _historyValueCell(row, signal),
                    ),
                  ),
              ]),
          ],
        ),
      ),
    );
  }

  Widget _historyValueCell(HistorySnapshotRecord row, TelemetrySignal liveSignal) {
    final stored = row.signal(liveSignal.name);
    if (stored == null) {
      return Text('-', style: TextStyle(color: Theme.of(context).disabledColor));
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Text(stored.valueText, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w700)),
        Text(stored.quality, maxLines: 1, overflow: TextOverflow.ellipsis, style: Theme.of(context).textTheme.labelSmall),
      ],
    );
  }

  Widget _eventSummaryCards(int shownCount) {
    final total = _asInt(summary?['total']);
    final warnings = _asInt(summary?['warning']) + _asInt(summary?['warnings']);
    final errors = _asInt(summary?['error']) + _asInt(summary?['errors']) + _asInt(summary?['critical']);
    return _metricGrid([
      MetricCard(title: 'Total Events', value: total.toString(), icon: Icons.event_note),
      MetricCard(title: 'Shown After UI Filter', value: shownCount.toString(), icon: Icons.visibility),
      MetricCard(title: 'Warnings', value: warnings.toString(), icon: Icons.warning_amber, good: warnings == 0),
      MetricCard(title: 'Errors/Faults', value: errors.toString(), icon: Icons.error_outline, good: errors == 0),
    ]);
  }

  Widget _eventFiltersCard() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Gateway event filters', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 12),
            Wrap(
              spacing: 12,
              runSpacing: 12,
              children: [
                _dropdown('Severity', query.severity, ['all', ...options.severities], (v) => setState(() => query = query.copyWith(severity: v == 'all' ? null : v, clearSeverity: v == 'all'))),
                _dropdown('Asset', query.assetId, ['all', ...assets.map((a) => a.assetId), ...options.assetIds], (v) => setState(() => query = query.copyWith(assetId: v == 'all' ? null : v, clearAssetId: v == 'all'))),
                _dropdown('Event Type', query.eventType, ['all', ...options.eventTypes], (v) => setState(() => query = query.copyWith(eventType: v == 'all' ? null : v, clearEventType: v == 'all'))),
                _dropdown('Source', query.source, ['all', ...options.sources], (v) => setState(() => query = query.copyWith(source: v == 'all' ? null : v, clearSource: v == 'all'))),
                _dropdown('Limit', query.limit.toString(), const ['50', '100', '200', '500'], (v) => setState(() => query = query.copyWith(limit: int.tryParse(v ?? '100') ?? 100))),
                _dropdown('Order', query.order, const ['desc', 'asc'], (v) => setState(() => query = query.copyWith(order: v ?? 'desc'))),
              ],
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 12,
              runSpacing: 12,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                SizedBox(width: 300, child: TextField(controller: eventSearchController, decoration: const InputDecoration(prefixIcon: Icon(Icons.search), labelText: 'Search message/event/payload'))),
                SizedBox(width: 250, child: TextField(controller: fromController, decoration: const InputDecoration(labelText: 'From time UTC'))),
                SizedBox(width: 250, child: TextField(controller: toController, decoration: const InputDecoration(labelText: 'To time UTC'))),
                FilledButton.icon(onPressed: refreshEvents, icon: const Icon(Icons.filter_alt), label: const Text('Apply')),
                OutlinedButton.icon(onPressed: _clearEvents, icon: const Icon(Icons.clear), label: const Text('Clear')),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _paginationControls() {
    final current = result;
    if (current == null) return const SizedBox.shrink();
    final canPrev = current.offset > 0;
    final canNext = current.offset + current.limit < current.total;
    return Row(
      mainAxisAlignment: MainAxisAlignment.end,
      children: [
        Text('Offset ${current.offset}'),
        const SizedBox(width: 12),
        OutlinedButton(onPressed: canPrev ? () { query = query.copyWith(offset: (current.offset - current.limit).clamp(0, current.total).toInt()); refreshEvents(); } : null, child: const Text('Previous')),
        const SizedBox(width: 8),
        OutlinedButton(onPressed: canNext ? () { query = query.copyWith(offset: current.offset + current.limit); refreshEvents(); } : null, child: const Text('Next')),
      ],
    );
  }

  Widget _dropdown(String label, String? value, List<String> rawItems, ValueChanged<String?> onChanged) {
    final items = rawItems.where((e) => e.trim().isNotEmpty).toSet().toList();
    final selected = value == null || value.isEmpty ? 'all' : value;
    if (!items.contains(selected)) items.insert(0, selected);
    return SizedBox(
      width: 210,
      child: DropdownButtonFormField<String>(
        value: selected,
        decoration: InputDecoration(labelText: label),
        items: [for (final item in items) DropdownMenuItem(value: item, child: Text(_prettyOption(item), overflow: TextOverflow.ellipsis))],
        onChanged: onChanged,
      ),
    );
  }

  Widget _signalCardGrid(List<TelemetrySignal> data, {bool compact = false}) {
    if (data.isEmpty) return const SizedBox.shrink();
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

  Widget _metricGrid(List<Widget> cards) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final crossAxisCount = constraints.maxWidth > 1250 ? 5 : constraints.maxWidth > 920 ? 3 : constraints.maxWidth > 620 ? 2 : 1;
        return GridView.count(
          crossAxisCount: crossAxisCount,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          childAspectRatio: constraints.maxWidth > 620 ? 2.45 : 3.8,
          children: cards,
        );
      },
    );
  }

  Widget _sectionHeader(String title, String subtitle) {
    return Row(children: [Text(title, style: Theme.of(context).textTheme.titleLarge), const SizedBox(width: 8), Chip(label: Text(subtitle))]);
  }

  String? _emptyToNull(String value) => value.trim().isEmpty ? null : value.trim();

  String _prettyOption(String item) {
    if (item == 'all') return 'All';
    if (item == 'desc') return 'Newest first';
    if (item == 'asc') return 'Oldest first';
    return item.replaceAll('_', ' ');
  }

  bool _isFaultAlarmSignal(TelemetrySignal signal) {
    final text = '${signal.name} ${signal.displayName} ${signal.category} ${signal.description ?? ''}'.toLowerCase();
    return text.contains('fault') || text.contains('alarm') || text.contains('warning') || text.contains('emergency') || signal.category.toLowerCase().contains('fault');
  }

  int _asInt(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '') ?? 0;
  }

  int _signalSort(TelemetrySignal a, TelemetrySignal b) {
    final c = a.category.compareTo(b.category);
    if (c != 0) return c;
    final aa = a.address ?? 99999999;
    final bb = b.address ?? 99999999;
    if (aa != bb) return aa.compareTo(bb);
    return a.displayName.compareTo(b.displayName);
  }
}

class _LogTile extends StatelessWidget {
  const _LogTile({required this.record});

  final LogRecord record;

  @override
  Widget build(BuildContext context) {
    final color = record.isWarningOrError ? Colors.orange : Theme.of(context).colorScheme.primary;
    return Card(
      child: ExpansionTile(
        leading: CircleAvatar(backgroundColor: color.withOpacity(0.13), foregroundColor: color, child: Icon(record.isWarningOrError ? Icons.warning_amber : Icons.event_note)),
        title: Text(record.message),
        subtitle: Text('${ValueFormatters.compactDateTime(record.timestampUtc)} • ${record.severity} • ${record.eventType} • ${record.source ?? '-'}${record.assetId == null ? '' : ' • ${record.assetId}'}'),
        trailing: Text('#${record.id}'),
        children: [Padding(padding: const EdgeInsets.all(12), child: JsonViewer(data: record.payload))],
      ),
    );
  }
}
