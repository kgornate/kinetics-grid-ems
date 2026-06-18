import 'package:flutter/material.dart';

import '../features/assets/widgets/widgets.dart';
import '../features/monitoring/widgets/monitoring_widgets.dart';
import '../models/models.dart';
import '../repositories/repositories.dart';

class HealthDashboardScreen extends StatefulWidget {
  final String gatewayIp;

  const HealthDashboardScreen({super.key, required this.gatewayIp});

  @override
  State<HealthDashboardScreen> createState() => _HealthDashboardScreenState();
}

class _HealthDashboardScreenState extends State<HealthDashboardScreen> {
  late final GatewayRepositoryBundle _repos = GatewayRepositoryBundle.forGateway(widget.gatewayIp);
  bool _loading = true;
  String? _error;
  GatewayHealthModel? _overall;
  AssetsHealthResponse? _assets;
  DiagnosticsResponse? _diagnostics;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final results = await Future.wait([
        _repos.health.fetchOverallHealth(),
        _repos.health.fetchAssetsHealth(),
        _repos.diagnostics.fetchDiagnostics(),
      ]);
      if (!mounted) return;
      setState(() {
        _overall = results[0] as GatewayHealthModel;
        _assets = results[1] as AssetsHealthResponse;
        _diagnostics = results[2] as DiagnosticsResponse;
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.toString();
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Health Dashboard'),
        actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh), tooltip: 'Refresh health'),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? _errorView()
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView(
                    padding: const EdgeInsets.all(18),
                    children: [
                      StatusSummaryCard(
                        title: 'Gateway Health',
                        status: _overall?.status ?? 'unknown',
                        icon: Icons.router,
                        subtitle: _overall?.recommendedAction,
                        children: [
                          _summaryWrap(_overall?.summary ?? const {}),
                        ],
                      ),
                      const SizedBox(height: 16),
                      Text('Asset Health', style: Theme.of(context).textTheme.titleLarge),
                      const SizedBox(height: 10),
                      ..._assetCards(),
                      const SizedBox(height: 16),
                      if (_overall != null) JsonPreviewCard(title: 'Gateway Health JSON', data: _overall!.raw),
                      if (_diagnostics != null) JsonPreviewCard(title: 'Diagnostics JSON', data: _diagnostics!.raw),
                    ],
                  ),
                ),
    );
  }

  Widget _errorView() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, color: Colors.red, size: 42),
            const SizedBox(height: 12),
            Text(_error!, textAlign: TextAlign.center),
            const SizedBox(height: 12),
            FilledButton.icon(onPressed: _load, icon: const Icon(Icons.refresh), label: const Text('Retry')),
          ],
        ),
      ),
    );
  }

  List<Widget> _assetCards() {
    final entries = _assets?.assets.entries.toList() ?? const [];
    if (entries.isEmpty) return [const Text('No asset health records received yet.')];
    return entries.map((entry) {
      final health = entry.value;
      final diag = _diagnostics?.diagnostics[entry.key] ?? _diagnostics?.diagnostics[health.assetId];
      return Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: StatusSummaryCard(
          title: health.assetId,
          status: health.status,
          icon: AssetStatusHelpers.iconForType(health.assetType),
          subtitle: health.reason,
          children: [
            if ((health.recommendedAction ?? '').isNotEmpty)
              Text('Action: ${health.recommendedAction}'),
            if (diag != null && (diag.recommendedAction ?? '').isNotEmpty)
              Text('Diagnostic: ${diag.recommendedAction}'),
            KeyValueTable(
              values: {
                'asset_type': health.assetType,
                'vendor': health.vendor,
                'protocol': health.protocol,
                'runtime_mode': health.runtimeMode,
                'running': health.running,
                'online': health.online,
                'last_error': health.lastError,
                'storage_status': health.storage['status'],
              },
              maxRows: 8,
            ),
          ],
        ),
      );
    }).toList(growable: false);
  }

  Widget _summaryWrap(Map<String, dynamic> summary) {
    if (summary.isEmpty) return const Text('No summary available');
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: summary.entries
          .map((entry) => Chip(label: Text('${entry.key}: ${entry.value}')))
          .toList(growable: false),
    );
  }
}
