import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/northbound_api_client.dart';
import '../models/log_filter_options.dart';
import '../models/log_record.dart';
import '../widgets/empty_state.dart';
import '../widgets/json_viewer.dart';
import '../widgets/metric_card.dart';

class LogsScreen extends StatefulWidget {
  const LogsScreen({super.key, required this.apiClient});

  final NorthboundApiClient apiClient;

  @override
  State<LogsScreen> createState() => _LogsScreenState();
}

class _LogsScreenState extends State<LogsScreen> {
  LogFilterOptions options = const LogFilterOptions();
  LogQuery query = const LogQuery(limit: 100);
  LogQueryResult? result;
  Map<String, dynamic>? summary;
  String? error;
  bool loading = false;

  final searchController = TextEditingController();
  final fromController = TextEditingController();
  final toController = TextEditingController();

  @override
  void initState() {
    super.initState();
    refreshAll();
  }

  @override
  void dispose() {
    searchController.dispose();
    fromController.dispose();
    toController.dispose();
    super.dispose();
  }

  Future<void> refreshAll() async {
    setState(() {
      loading = true;
      error = null;
    });

    final filterResult = await widget.apiClient.getLogFilterOptions();
    final summaryResult = await widget.apiClient.getLogSummary(
      fromTime: _emptyToNull(fromController.text),
      toTime: _emptyToNull(toController.text),
    );
    final logsResult = await widget.apiClient.getLogs(_queryFromUi());

    if (!mounted) return;
    setState(() {
      loading = false;
      if (filterResult.isSuccess) options = filterResult.data ?? const LogFilterOptions();
      if (summaryResult.isSuccess) summary = summaryResult.data;
      if (logsResult.isSuccess) result = logsResult.data;
      error = filterResult.error ?? summaryResult.error ?? logsResult.error;
    });
  }

  LogQuery _queryFromUi({int? offset}) {
    return query.copyWith(
      fromTime: _emptyToNull(fromController.text),
      toTime: _emptyToNull(toController.text),
      search: _emptyToNull(searchController.text),
      offset: offset ?? query.offset,
      clearFromTime: _emptyToNull(fromController.text) == null,
      clearToTime: _emptyToNull(toController.text) == null,
      clearSearch: _emptyToNull(searchController.text) == null,
    );
  }

  void _clearFilters() {
    searchController.clear();
    fromController.clear();
    toController.clear();
    setState(() {
      query = const LogQuery(limit: 100);
    });
    refreshAll();
  }

  Future<void> _showExportUrl() async {
    final url = widget.apiClient.logExportUrl(_queryFromUi(offset: 0));
    await Clipboard.setData(ClipboardData(text: url));
    if (!mounted) return;
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('CSV export URL copied'),
        content: SelectableText(url),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final items = result?.items ?? const <LogRecord>[];
    return Scaffold(
      appBar: AppBar(
        title: const Text('Logs & Filters'),
        actions: [
          IconButton(tooltip: 'Copy CSV export URL', onPressed: _showExportUrl, icon: const Icon(Icons.download)),
          IconButton(tooltip: 'Refresh logs', onPressed: refreshAll, icon: const Icon(Icons.refresh)),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: refreshAll,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _summaryCards(),
            const SizedBox(height: 12),
            _filtersCard(),
            const SizedBox(height: 12),
            if (loading) const LinearProgressIndicator(),
            if (error != null) Card(child: ListTile(leading: const Icon(Icons.error), title: Text(error!))),
            const SizedBox(height: 8),
            Row(
              children: [
                Text('Results', style: Theme.of(context).textTheme.headlineSmall),
                const SizedBox(width: 8),
                Chip(label: Text('${result?.total ?? 0} total')),
                Chip(label: Text('${items.length} shown')),
              ],
            ),
            const SizedBox(height: 8),
            if (items.isEmpty && !loading)
              const EmptyState(title: 'No logs found', subtitle: 'Try clearing filters or increasing the limit.')
            else
              for (final item in items) _LogTile(record: item),
            const SizedBox(height: 12),
            _paginationControls(),
          ],
        ),
      ),
    );
  }

  Widget _summaryCards() {
    final total = summary?['total']?.toString() ?? '-';
    final bySeverity = summary?['by_severity'] is Map ? Map<String, dynamic>.from(summary!['by_severity'] as Map) : const <String, dynamic>{};
    final errors = _mapCount(bySeverity, 'error') + _mapCount(bySeverity, 'critical') + _mapCount(bySeverity, 'fault');
    final warnings = _mapCount(bySeverity, 'warning');
    return LayoutBuilder(
      builder: (context, constraints) {
        final wide = constraints.maxWidth > 900;
        final children = [
          MetricCard(title: 'Total Logs', value: total, icon: Icons.article_outlined),
          MetricCard(title: 'Warnings', value: warnings.toString(), icon: Icons.warning_amber, good: warnings == 0),
          MetricCard(title: 'Errors/Faults', value: errors.toString(), icon: Icons.error_outline, good: errors == 0),
          MetricCard(title: 'Query Limit', value: query.limit.toString(), icon: Icons.filter_alt_outlined),
        ];
        if (!wide) return Column(children: children.map((c) => Padding(padding: const EdgeInsets.only(bottom: 8), child: c)).toList());
        return Row(children: children.map((c) => Expanded(child: Padding(padding: const EdgeInsets.only(right: 8), child: c))).toList());
      },
    );
  }

  Widget _filtersCard() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Filters', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 12),
            Wrap(
              spacing: 12,
              runSpacing: 12,
              children: [
                _dropdown('Severity', query.severity, options.severities, (v) => setState(() => query = query.copyWith(severity: v, clearSeverity: v == null))),
                _dropdown('Asset', query.assetId, options.assetIds, (v) => setState(() => query = query.copyWith(assetId: v, clearAssetId: v == null))),
                _dropdown('Event Type', query.eventType, options.eventTypes, (v) => setState(() => query = query.copyWith(eventType: v, clearEventType: v == null))),
                _dropdown('Source', query.source, options.sources, (v) => setState(() => query = query.copyWith(source: v, clearSource: v == null))),
                SizedBox(
                  width: 180,
                  child: DropdownButtonFormField<int>(
                    value: query.limit,
                    decoration: const InputDecoration(labelText: 'Limit'),
                    items: const [50, 100, 200, 500].map((v) => DropdownMenuItem(value: v, child: Text('$v rows'))).toList(),
                    onChanged: (v) => setState(() => query = query.copyWith(limit: v ?? 100, offset: 0)),
                  ),
                ),
                SizedBox(
                  width: 160,
                  child: DropdownButtonFormField<String>(
                    value: query.order,
                    decoration: const InputDecoration(labelText: 'Order'),
                    items: const [
                      DropdownMenuItem(value: 'desc', child: Text('Newest first')),
                      DropdownMenuItem(value: 'asc', child: Text('Oldest first')),
                    ],
                    onChanged: (v) => setState(() => query = query.copyWith(order: v ?? 'desc', offset: 0)),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 12,
              runSpacing: 12,
              children: [
                SizedBox(
                  width: 260,
                  child: TextField(
                    controller: searchController,
                    decoration: const InputDecoration(labelText: 'Search message/event/payload', prefixIcon: Icon(Icons.search)),
                    onSubmitted: (_) => refreshAll(),
                  ),
                ),
                SizedBox(
                  width: 240,
                  child: TextField(
                    controller: fromController,
                    decoration: const InputDecoration(labelText: 'From time UTC', hintText: '2026-06-30T00:00:00'),
                    onSubmitted: (_) => refreshAll(),
                  ),
                ),
                SizedBox(
                  width: 240,
                  child: TextField(
                    controller: toController,
                    decoration: const InputDecoration(labelText: 'To time UTC', hintText: '2026-06-30T23:59:59'),
                    onSubmitted: (_) => refreshAll(),
                  ),
                ),
                FilledButton.icon(onPressed: () { setState(() => query = _queryFromUi(offset: 0)); refreshAll(); }, icon: const Icon(Icons.filter_alt), label: const Text('Apply')),
                OutlinedButton.icon(onPressed: _clearFilters, icon: const Icon(Icons.clear), label: const Text('Clear')),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _dropdown(String label, String? value, List<String> items, ValueChanged<String?> onChanged) {
    return SizedBox(
      width: 220,
      child: DropdownButtonFormField<String?>(
        value: value,
        decoration: InputDecoration(labelText: label),
        items: [
          const DropdownMenuItem<String?>(value: null, child: Text('All')),
          for (final item in items) DropdownMenuItem<String?>(value: item, child: Text(item, overflow: TextOverflow.ellipsis)),
        ],
        onChanged: onChanged,
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
        OutlinedButton(
          onPressed: canPrev ? () { setState(() => query = query.copyWith(offset: (current.offset - current.limit).clamp(0, current.total).toInt())); refreshAll(); } : null,
          child: const Text('Previous'),
        ),
        const SizedBox(width: 8),
        FilledButton(
          onPressed: canNext ? () { setState(() => query = query.copyWith(offset: current.offset + current.limit)); refreshAll(); } : null,
          child: const Text('Next'),
        ),
      ],
    );
  }

  static String? _emptyToNull(String value) => value.trim().isEmpty ? null : value.trim();

  static int _mapCount(Map<String, dynamic> map, String key) {
    final value = map[key];
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '') ?? 0;
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
        leading: CircleAvatar(
          backgroundColor: color.withOpacity(0.14),
          foregroundColor: color,
          child: Icon(record.isWarningOrError ? Icons.warning_amber : Icons.event_note, size: 20),
        ),
        title: Text(record.message.isEmpty ? record.eventType : record.message, maxLines: 1, overflow: TextOverflow.ellipsis),
        subtitle: Text('${record.timestampUtc} • ${record.severity} • ${record.eventType} • ${record.assetId ?? 'gateway'}'),
        trailing: Text('#${record.id}'),
        childrenPadding: const EdgeInsets.all(16),
        children: [
          Align(
            alignment: Alignment.centerLeft,
            child: Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                Chip(label: Text('severity: ${record.severity}')),
                Chip(label: Text('event: ${record.eventType}')),
                Chip(label: Text('source: ${record.source ?? '-'}')),
                Chip(label: Text('asset: ${record.assetId ?? '-'}')),
              ],
            ),
          ),
          const SizedBox(height: 8),
          JsonViewer(data: record.payload),
        ],
      ),
    );
  }
}
