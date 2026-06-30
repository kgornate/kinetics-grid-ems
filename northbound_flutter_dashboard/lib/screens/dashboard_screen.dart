import 'dart:async';

import 'package:flutter/material.dart';

import '../api/northbound_api_client.dart';
import '../api/telemetry_ws_client.dart';
import '../models/asset_summary.dart';
import '../models/signal_preview.dart';
import '../models/storage_status.dart';
import '../utils/key_signal_parser.dart';
import '../widgets/asset_card.dart';
import '../widgets/json_viewer.dart';
import '../widgets/status_chip.dart';
import 'alarms_screen.dart';
import 'asset_telemetry_screen.dart';
import 'logs_screen.dart';
import 'settings_screen.dart';
import 'storage_screen.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({
    super.key,
    required this.apiClient,
    required this.wsClient,
    required this.onConfigChanged,
    required this.apiBaseUrl,
    required this.wsUrl,
  });

  final NorthboundApiClient apiClient;
  final TelemetryWsClient wsClient;
  final void Function(String apiBaseUrl, String wsUrl) onConfigChanged;
  final String apiBaseUrl;
  final String wsUrl;

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  Map<String, dynamic>? health;
  Map<String, dynamic>? keySignals;
  Map<String, List<SignalPreview>> keySignalsByAsset = const {};
  List<AssetSummary> assets = [];
  int alarmCount = 0;
  StorageStatus? storageStatus;
  String? error;
  bool loading = false;
  Timer? refreshTimer;

  StreamSubscription? wsSub;
  StreamSubscription? wsStatusSub;
  int wsFrames = 0;
  DateTime? lastWsFrame;
  String wsStatus = 'disconnected';
  String? wsError;
  int? nextRetryInSec;

  @override
  void initState() {
    super.initState();
    refreshAll();
    refreshTimer = Timer.periodic(const Duration(seconds: 3), (_) => refreshAll());
    _connectWebSocket(resetCounter: true);
  }

  @override
  void didUpdateWidget(covariant DashboardScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.wsUrl != widget.wsUrl || oldWidget.wsClient != widget.wsClient) {
      _connectWebSocket(resetCounter: true);
    }
  }

  @override
  void dispose() {
    refreshTimer?.cancel();
    wsSub?.cancel();
    wsStatusSub?.cancel();
    super.dispose();
  }

  Future<void> refreshAll() async {
    setState(() {
      loading = true;
      error = null;
    });
    final healthResult = await widget.apiClient.getHealth();
    final assetResult = await widget.apiClient.getAssets();
    final keyResult = await widget.apiClient.getKeySignals();
    final alarmResult = await widget.apiClient.getAlarms();
    final storageResult = await widget.apiClient.getStorageStatus();

    if (!mounted) return;
    setState(() {
      loading = false;
      if (healthResult.isSuccess) health = healthResult.data;
      if (assetResult.isSuccess) assets = assetResult.data ?? [];
      if (keyResult.isSuccess) {
        keySignals = keyResult.data;
        final parsed = KeySignalParser.byAsset(keyResult.data);
        if (parsed.isNotEmpty) keySignalsByAsset = parsed;
      }
      if (alarmResult.isSuccess) alarmCount = alarmResult.data?.length ?? 0;
      if (storageResult.isSuccess) storageStatus = storageResult.data;
      error = healthResult.error ?? assetResult.error ?? keyResult.error ?? alarmResult.error ?? storageResult.error;
    });
  }

  void _connectWebSocket({bool resetCounter = false}) {
    wsSub?.cancel();
    wsStatusSub?.cancel();

    if (mounted) {
      setState(() {
        wsStatus = 'connecting';
        wsError = null;
        nextRetryInSec = null;
        if (resetCounter) {
          wsFrames = 0;
          lastWsFrame = null;
        }
      });
    }

    // Subscribe before connect so the first frame/status cannot be missed.
    wsSub = widget.wsClient.stream.listen(
      (event) {
        if (!mounted) return;
        setState(() {
          wsFrames++;
          lastWsFrame = DateTime.now();
          wsStatus = 'connected';
          wsError = null;
          nextRetryInSec = null;
          keySignals = event;
          final parsed = KeySignalParser.byAsset(event);
          if (parsed.isNotEmpty) keySignalsByAsset = parsed;
        });
      },
      onError: (e) {
        if (!mounted) return;
        setState(() {
          wsStatus = 'error';
          wsError = e.toString();
        });
      },
    );

    wsStatusSub = widget.wsClient.statusStream.listen((status) {
      if (!mounted) return;
      setState(() {
        wsStatus = status.state;
        wsError = status.lastError;
        nextRetryInSec = status.nextRetryInSec;
      });
    });

    widget.wsClient.connect();
  }

  @override
  Widget build(BuildContext context) {
    final badSignals = _asInt(health?['bad_signal_count']);
    final good = health != null && badSignals == 0;
    return Scaffold(
      appBar: AppBar(
        title: const Text('NorthBound EMS Dashboard'),
        actions: [
          IconButton(
            tooltip: 'Reconnect WebSocket',
            icon: const Icon(Icons.link),
            onPressed: () => _connectWebSocket(resetCounter: true),
          ),
          IconButton(
            tooltip: 'Logs & Filters',
            icon: const Icon(Icons.article_outlined),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => LogsScreen(apiClient: widget.apiClient)),
            ),
          ),
          IconButton(
            tooltip: 'Storage / Historian',
            icon: const Icon(Icons.storage),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => StorageScreen(apiClient: widget.apiClient)),
            ),
          ),
          IconButton(
            tooltip: 'Alarms',
            icon: Badge(
              isLabelVisible: alarmCount > 0,
              label: Text(alarmCount.toString()),
              child: const Icon(Icons.notifications_active),
            ),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => AlarmsScreen(apiClient: widget.apiClient)),
            ),
          ),
          IconButton(
            tooltip: 'Settings',
            icon: const Icon(Icons.settings),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => SettingsScreen(
                  apiBaseUrl: widget.apiBaseUrl,
                  wsUrl: widget.wsUrl,
                  onApply: widget.onConfigChanged,
                ),
              ),
            ),
          ),
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: refreshAll,
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: refreshAll,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                StatusChip(label: good ? 'Gateway OK' : 'Check gateway', good: good),
                const StatusChip(label: 'Read-only', good: true),
                StatusChip(
                  label: 'WS $wsStatus: $wsFrames',
                  good: wsStatus == 'connected' && wsFrames > 0,
                  icon: _wsIcon(),
                ),
                StatusChip(label: 'Alarms: $alarmCount', good: alarmCount == 0),
                StatusChip(label: _storageLabel(), good: storageStatus?.canWrite == true, icon: Icons.storage),
                Chip(label: Text(_connectionLabel(widget.apiBaseUrl))),
                if (lastWsFrame != null) Chip(label: Text('Last WS: ${lastWsFrame!.toLocal()}')),
                if (nextRetryInSec != null) Chip(label: Text('Retry in ${nextRetryInSec}s')),
              ],
            ),
            const SizedBox(height: 12),
            if (loading) const LinearProgressIndicator(),
            if (error != null) Card(child: ListTile(leading: const Icon(Icons.error), title: Text(error!))),
            if (wsError != null)
              Card(
                child: ListTile(
                  leading: const Icon(Icons.error_outline),
                  title: const Text('WebSocket issue'),
                  subtitle: Text(wsError!),
                  trailing: TextButton(onPressed: () => _connectWebSocket(resetCounter: true), child: const Text('Reconnect')),
                ),
              ),
            _healthPanel(),
            const SizedBox(height: 16),
            Row(
              children: [
                Text('Assets', style: Theme.of(context).textTheme.headlineSmall),
                const SizedBox(width: 8),
                Chip(label: Text('${assets.length} cards')),
              ],
            ),
            const SizedBox(height: 8),
            LayoutBuilder(
              builder: (context, constraints) {
                final width = constraints.maxWidth;
                final crossAxisCount = width > 1320 ? 4 : width > 920 ? 3 : width > 620 ? 2 : 1;
                return GridView.count(
                  crossAxisCount: crossAxisCount,
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  childAspectRatio: width > 620 ? 1.35 : 1.65,
                  children: [
                    for (final asset in assets)
                      AssetCard(
                        asset: asset,
                        previewSignals: _previewSignalsFor(asset),
                        onTap: () => Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => AssetTelemetryScreen(apiClient: widget.apiClient, asset: asset),
                          ),
                        ),
                      ),
                  ],
                );
              },
            ),
            const SizedBox(height: 16),
            ExpansionTile(
              title: const Text('Raw key-signal / WebSocket payload'),
              children: [JsonViewer(data: keySignals ?? {})],
            ),
          ],
        ),
      ),
    );
  }

  IconData _wsIcon() {
    switch (wsStatus) {
      case 'connected':
        return Icons.link;
      case 'connecting':
      case 'reconnecting':
        return Icons.sync;
      case 'error':
        return Icons.error;
      default:
        return Icons.link_off;
    }
  }

  List<SignalPreview> _previewSignalsFor(AssetSummary asset) {
    final parsed = keySignalsByAsset[asset.assetId];
    if (parsed != null && parsed.isNotEmpty) return parsed;
    if (asset.keySignals.isEmpty) return const [];
    return asset.keySignals.entries.map((entry) => SignalPreview.fromEntry(entry.key.toString(), entry.value)).toList();
  }

  Widget _healthPanel() {
    if (health == null) return const Card(child: ListTile(title: Text('No health data yet')));
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Gateway Health', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            Wrap(
              spacing: 16,
              runSpacing: 8,
              children: [
                Text('Mode: ${health!['gateway_mode']}'),
                Text('Assets: ${health!['online_asset_count']}/${health!['asset_count']} online'),
                Text('Signals: ${health!['total_signal_count']}'),
                Text('Bad: ${health!['bad_signal_count']}'),
                Text('Alarms: $alarmCount'),
                Text('Commands: ${health!['commands_enabled']}'),
                Text('Storage: ${storageStatus?.canWrite == true ? 'writable' : 'check'}'),
              ],
            ),
          ],
        ),
      ),
    );
  }

  String _storageLabel() {
    if (storageStatus == null) return 'Storage: unknown';
    if (storageStatus!.canWrite) return 'Storage: OK';
    return 'Storage: check';
  }

  static int _asInt(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '') ?? 0;
  }

  static String _connectionLabel(String url) {
    return url.contains('ems-api.unityess.cloud') ? 'Cloudflare' : 'Local eth0';
  }
}
