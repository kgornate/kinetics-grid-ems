import 'package:flutter/material.dart';

import '../api/northbound_api_client.dart';
import '../models/storage_status.dart';
import '../widgets/json_viewer.dart';
import '../widgets/metric_card.dart';

class StorageScreen extends StatefulWidget {
  const StorageScreen({super.key, required this.apiClient});

  final NorthboundApiClient apiClient;

  @override
  State<StorageScreen> createState() => _StorageScreenState();
}

class _StorageScreenState extends State<StorageScreen> {
  StorageStatus? status;
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
    final result = await widget.apiClient.getStorageStatus();
    if (!mounted) return;
    setState(() {
      loading = false;
      if (result.isSuccess) status = result.data;
      error = result.error;
    });
  }

  @override
  Widget build(BuildContext context) {
    final s = status;
    return Scaffold(
      appBar: AppBar(title: const Text('Storage / Historian'), actions: [IconButton(onPressed: refresh, icon: const Icon(Icons.refresh))]),
      body: RefreshIndicator(
        onRefresh: refresh,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (loading) const LinearProgressIndicator(),
            if (error != null) Card(child: ListTile(leading: const Icon(Icons.error), title: Text(error!))),
            if (s == null)
              const Card(child: ListTile(title: Text('No storage status loaded yet')))
            else ...[
              _statusBanner(s),
              const SizedBox(height: 12),
              _metricGrid(s),
              const SizedBox(height: 12),
              _detailsCard(s),
              const SizedBox(height: 12),
              ExpansionTile(title: const Text('Raw storage status JSON'), children: [JsonViewer(data: s.raw)]),
            ],
          ],
        ),
      ),
    );
  }

  Widget _statusBanner(StorageStatus s) {
    final good = s.enabled && s.canWrite && s.mountOk && s.reasons.isEmpty;
    return Card(
      child: ListTile(
        leading: Icon(good ? Icons.check_circle : Icons.warning, color: good ? Colors.green : Colors.orange),
        title: Text(good ? 'Storage healthy and writable' : 'Storage needs attention'),
        subtitle: Text(s.reasons.isEmpty ? s.path : s.reasons.join('\n')),
      ),
    );
  }

  Widget _metricGrid(StorageStatus s) {
    final cards = [
      MetricCard(title: 'Write Status', value: s.canWrite ? 'Writable' : 'Blocked', icon: Icons.edit_note, good: s.canWrite),
      MetricCard(title: 'Mount', value: s.mountOk ? 'OK' : 'Missing', icon: Icons.sd_storage, good: s.mountOk),
      MetricCard(title: 'DB Size', value: '${s.dbSizeMb ?? '-'} MB', icon: Icons.data_object),
      MetricCard(title: 'Free Space', value: '${s.freeSpaceMb ?? '-'} MB', icon: Icons.storage),
      MetricCard(title: 'Retention', value: '${s.retentionDays ?? '-'} days', icon: Icons.history),
      MetricCard(title: 'Snapshot Interval', value: '${s.snapshotIntervalSec ?? '-'} sec', icon: Icons.timer),
    ];
    return LayoutBuilder(
      builder: (context, constraints) {
        final crossAxisCount = constraints.maxWidth > 1100 ? 3 : constraints.maxWidth > 720 ? 2 : 1;
        return GridView.count(
          crossAxisCount: crossAxisCount,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          childAspectRatio: constraints.maxWidth > 720 ? 3.0 : 4.5,
          children: cards,
        );
      },
    );
  }

  Widget _detailsCard(StorageStatus s) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Tables', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            if (s.tables.isEmpty)
              const Text('No table counts available')
            else
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [for (final e in s.tables.entries) Chip(label: Text('${e.key}: ${e.value}'))],
              ),
            const SizedBox(height: 16),
            Text('Configuration', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            SelectableText('Path: ${s.path}\nMode: ${s.storeMode ?? '-'}\nSkipped writes: ${s.skippedWriteCount ?? 0}\nLast skip reason: ${s.lastSkipReason ?? '-'}'),
          ],
        ),
      ),
    );
  }
}
