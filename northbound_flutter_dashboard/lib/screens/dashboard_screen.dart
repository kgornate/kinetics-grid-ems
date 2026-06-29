import 'dart:async';

import 'package:flutter/material.dart';

import '../api/northbound_api_client.dart';
import '../api/telemetry_ws_client.dart';
import '../models/asset_summary.dart';
import '../models/signal_preview.dart';
import '../utils/key_signal_parser.dart';
import '../widgets/asset_card.dart';
import '../widgets/json_viewer.dart';
import '../widgets/status_chip.dart';
import 'alarms_screen.dart';
import 'asset_telemetry_screen.dart';
import 'settings_screen.dart';

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
  String? error;
  bool loading = false;
  Timer? refreshTimer;
  StreamSubscription? wsSub;
  int wsFrames = 0;
  DateTime? lastWsFrame;

  @override
  void initState() {
    super.initState();
    refreshAll();
    refreshTimer = Timer.periodic(const Duration(seconds: 3), (_) => refreshAll());
    widget.wsClient.connect();
    wsSub = widget.wsClient.stream.listen((event) {
      setState(() {
        wsFrames++;
        lastWsFrame = DateTime.now();
        keySignals = event;
        final parsed = KeySignalParser.byAsset(event);
        if (parsed.isNotEmpty) keySignalsByAsset = parsed;
      });
    }, onError: (e) {
      setState(() => error = 'WebSocket error: $e');
    });
  }

  @override
  void dispose() {
    refreshTimer?.cancel();
    wsSub?.cancel();
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

    if (!mounted) return;
    setState(() {
      loading = false;
      if (healthResult.isSuccess) health = healthResult.data;
      if (assetResult.isSuccess) assets = assetResult.data ?? [];
      if (keyResult.isSuccess) {
        keySignals = keyResult.data;
        keySignalsByAsset = KeySignalParser.byAsset(keyResult.data);
      }
      if (alarmResult.isSuccess) alarmCount = alarmResult.data?.length ?? 0;
      error = healthResult.error ?? assetResult.error ?? keyResult.error ?? alarmResult.error;
    });
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
                StatusChip(label: 'Read-only', good: true),
                StatusChip(label: 'WS frames: $wsFrames', good: wsFrames > 0),
                StatusChip(label: 'Alarms: $alarmCount', good: alarmCount == 0),
                Chip(label: Text(_connectionLabel(widget.apiBaseUrl))),
                if (lastWsFrame != null) Chip(label: Text('Last WS: ${lastWsFrame!.toLocal()}')),
              ],
            ),
            const SizedBox(height: 12),
            if (loading) const LinearProgressIndicator(),
            if (error != null) Card(child: ListTile(leading: const Icon(Icons.error), title: Text(error!))),
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
              title: const Text('Raw key-signal payload'),
              children: [JsonViewer(data: keySignals ?? {})],
            ),
          ],
        ),
      ),
    );
  }

  List<SignalPreview> _previewSignalsFor(AssetSummary asset) {
    final parsed = keySignalsByAsset[asset.assetId];
    if (parsed != null && parsed.isNotEmpty) return parsed;
    if (asset.keySignals.isEmpty) return const [];
    return asset.keySignals.entries
        .map((entry) => SignalPreview.fromEntry(entry.key.toString(), entry.value))
        .toList();
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
              ],
            ),
          ],
        ),
      ),
    );
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
