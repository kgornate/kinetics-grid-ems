import 'package:flutter/material.dart';

import '../features/assets/widgets/widgets.dart';
import '../features/monitoring/widgets/monitoring_widgets.dart';
import '../models/models.dart';
import '../repositories/repositories.dart';

class AssetDetailScreen extends StatefulWidget {
  final String gatewayIp;
  final AssetModel asset;

  const AssetDetailScreen({super.key, required this.gatewayIp, required this.asset});

  @override
  State<AssetDetailScreen> createState() => _AssetDetailScreenState();
}

class _AssetDetailScreenState extends State<AssetDetailScreen> {
  late final GatewayRepositoryBundle _repos = GatewayRepositoryBundle.forGateway(widget.gatewayIp);
  bool _loading = true;
  String? _error;
  AssetHealthModel? _health;
  AssetDiagnosticsResponse? _diagnostics;
  AssetTelemetryResponse? _telemetry;
  Map<String, dynamic>? _storageHealth;

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
    final errors = <String>[];
    AssetHealthModel? health;
    AssetDiagnosticsResponse? diagnostics;
    AssetTelemetryResponse? telemetry;
    Map<String, dynamic>? storageHealth;

    try {
      health = await _repos.health.fetchAssetHealth(widget.asset.assetId);
    } catch (error) {
      errors.add('health: $error');
    }
    try {
      diagnostics = await _repos.diagnostics.fetchAssetDiagnostics(widget.asset.assetId);
    } catch (error) {
      errors.add('diagnostics: $error');
    }
    try {
      telemetry = await _repos.telemetry.fetchAssetOperatorTelemetry(widget.asset.assetId);
    } catch (error) {
      errors.add('operator telemetry: $error');
    }
    try {
      storageHealth = await _repos.logs.fetchStorageHealth(assetId: widget.asset.assetId);
    } catch (error) {
      errors.add('storage health: $error');
    }

    if (!mounted) return;
    setState(() {
      _health = health;
      _diagnostics = diagnostics;
      _telemetry = telemetry;
      _storageHealth = storageHealth;
      _error = errors.isEmpty ? null : errors.join('\n');
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final health = _health;
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.asset.assetId),
        actions: [IconButton(onPressed: _load, icon: const Icon(Icons.refresh))],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
                  padding: const EdgeInsets.all(18),
                  children: [
                    if (_error != null && _error!.isNotEmpty) ...[
                      Card(
                        color: Colors.orange.withOpacity(0.08),
                        child: Padding(
                          padding: const EdgeInsets.all(12),
                          child: Text('Some asset details were unavailable:\n$_error'),
                        ),
                      ),
                      const SizedBox(height: 12),
                    ],
                    StatusSummaryCard(
                      title: widget.asset.assetId,
                      status: health?.status ?? (widget.asset.online ? 'healthy' : 'unknown'),
                      icon: AssetStatusHelpers.iconForType(widget.asset.assetType),
                      subtitle: health?.reason,
                      children: [
                        if ((health?.recommendedAction ?? '').isNotEmpty)
                          Text('Recommended action: ${health!.recommendedAction}'),
                        KeyValueTable(
                          values: {
                            'asset_type': widget.asset.assetType,
                            'asset_key': widget.asset.assetKey,
                            'vendor': widget.asset.vendor,
                            'protocol': widget.asset.protocol,
                            'profile': widget.asset.profile,
                            'runtime_mode': widget.asset.runtimeMode,
                            'enabled': widget.asset.enabled,
                            'running': widget.asset.running,
                            'online': widget.asset.online,
                          },
                          maxRows: 12,
                        ),
                      ],
                    ),
                    const SizedBox(height: 14),
                    StatusSummaryCard(
                      title: 'Operator Telemetry',
                      status: _telemetry?.status ?? 'unknown',
                      icon: Icons.monitor_heart,
                      subtitle: 'Clean telemetry view for operators.',
                      children: [
                        KeyValueTable(values: _telemetry?.telemetry ?? const {}, maxRows: 18),
                      ],
                    ),
                    const SizedBox(height: 14),
                    StatusSummaryCard(
                      title: 'Storage Health',
                      status: _storageHealth?['status']?.toString() ?? 'unknown',
                      icon: Icons.storage,
                      subtitle: _storageHealth?['message']?.toString(),
                      children: [KeyValueTable(values: _storageHealth ?? const {}, maxRows: 12)],
                    ),
                    const SizedBox(height: 14),
                    if (_diagnostics?.diagnostics != null)
                      StatusSummaryCard(
                        title: 'Diagnostics',
                        status: _diagnostics!.diagnostics!.status,
                        icon: Icons.troubleshoot,
                        subtitle: _diagnostics!.diagnostics!.reason,
                        children: [
                          if ((_diagnostics!.diagnostics!.recommendedAction ?? '').isNotEmpty)
                            Text('Action: ${_diagnostics!.diagnostics!.recommendedAction}'),
                        ],
                      ),
                    const SizedBox(height: 14),
                    if (_telemetry != null) JsonPreviewCard(title: 'Telemetry JSON', data: _telemetry!.raw),
                    if (health != null) JsonPreviewCard(title: 'Health JSON', data: health.raw),
                  ],
                ),
    );
  }
}
