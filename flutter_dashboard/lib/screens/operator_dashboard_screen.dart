import 'package:flutter/material.dart';

import '../features/assets/widgets/widgets.dart';
import '../features/monitoring/widgets/monitoring_widgets.dart';
import '../models/models.dart';
import '../repositories/repositories.dart';

class OperatorDashboardScreen extends StatefulWidget {
  final String gatewayIp;

  const OperatorDashboardScreen({super.key, required this.gatewayIp});

  @override
  State<OperatorDashboardScreen> createState() => _OperatorDashboardScreenState();
}

class _OperatorDashboardScreenState extends State<OperatorDashboardScreen> {
  late final GatewayRepositoryBundle _repos = GatewayRepositoryBundle.forGateway(widget.gatewayIp);
  bool _loading = true;
  String? _error;
  TelemetryEnvelope? _operatorTelemetry;
  AssetListResponse? _assets;
  AssetsHealthResponse? _health;

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
        _repos.telemetry.fetchOperatorTelemetry(),
        _repos.assets.fetchAssets(),
        _repos.health.fetchAssetsHealth(),
      ]);
      if (!mounted) return;
      setState(() {
        _operatorTelemetry = results[0] as TelemetryEnvelope;
        _assets = results[1] as AssetListResponse;
        _health = results[2] as AssetsHealthResponse;
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
        title: const Text('Operator Mode Dashboard'),
        actions: [IconButton(onPressed: _load, icon: const Icon(Icons.refresh))],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text(_error!))
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView(
                    padding: const EdgeInsets.all(18),
                    children: [
                      StatusSummaryCard(
                        title: 'Operator Telemetry View',
                        status: _operatorTelemetry?.status ?? 'unknown',
                        icon: Icons.visibility,
                        subtitle: 'Filtered telemetry for operator dashboards. Raw/debug fields are hidden by backend.',
                        children: [
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: [
                              Chip(label: Text('Gateway: ${_operatorTelemetry?.gatewayId ?? '--'}')),
                              Chip(label: Text('Timestamp: ${_operatorTelemetry?.timestamp ?? '--'}')),
                              Chip(label: Text('View: ${_operatorTelemetry?.view ?? 'operator'}')),
                            ],
                          ),
                        ],
                      ),
                      const SizedBox(height: 16),
                      ..._assetTelemetryCards(),
                      const SizedBox(height: 16),
                      if (_operatorTelemetry != null)
                        JsonPreviewCard(
                          title: 'Operator Telemetry JSON',
                          data: _operatorTelemetry!.raw,
                        ),
                    ],
                  ),
                ),
    );
  }

  List<Widget> _assetTelemetryCards() {
    final assets = _assets?.assets ?? const <AssetModel>[];
    if (assets.isEmpty) return [const Text('No asset catalog received yet.')];
    return assets.map((asset) {
      final health = _health?.assets[asset.assetId] ?? _health?.assets[asset.assetKey];
      final telemetry = _operatorTelemetry?.telemetryForAsset(asset.assetId) ?? const <String, dynamic>{};
      final status = health?.status ?? (asset.online ? 'healthy' : 'unknown');
      return Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: StatusSummaryCard(
          title: asset.assetId,
          status: status,
          icon: AssetStatusHelpers.iconForType(asset.assetType),
          subtitle: '${asset.assetType} • ${asset.protocol ?? '--'} • ${asset.runtimeMode}',
          children: [
            if ((health?.recommendedAction ?? '').isNotEmpty)
              Text('Action: ${health!.recommendedAction}'),
            KeyValueTable(
              values: telemetry,
              preferredKeys: const [
                'communication_status',
                'comm_status',
                'status',
                'soc_percent',
                'pack_voltage_v',
                'pack_current_a',
                'active_power_kw',
                'dc_voltage_v',
                'outlet_water_temp',
                'return_water_temp',
                'fault_code',
                'fault_active',
                'fault_description',
              ],
              maxRows: 14,
            ),
          ],
        ),
      );
    }).toList(growable: false);
  }
}
