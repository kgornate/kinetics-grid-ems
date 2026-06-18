import 'package:flutter/material.dart';

import '../features/assets/widgets/widgets.dart';
import '../features/monitoring/widgets/monitoring_widgets.dart';
import '../models/models.dart';
import '../repositories/repositories.dart';

class StorageHealthScreen extends StatefulWidget {
  final String gatewayIp;

  const StorageHealthScreen({super.key, required this.gatewayIp});

  @override
  State<StorageHealthScreen> createState() => _StorageHealthScreenState();
}

class _StorageHealthScreenState extends State<StorageHealthScreen> {
  late final GatewayRepositoryBundle _repos = GatewayRepositoryBundle.forGateway(widget.gatewayIp);
  bool _loading = true;
  String? _error;
  AssetListResponse? _assets;
  final Map<String, Map<String, dynamic>> _healthByAsset = {};

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
      final assets = await _repos.assets.fetchAssets();
      final health = <String, Map<String, dynamic>>{};
      for (final asset in assets.assets) {
        health[asset.assetId] = await _repos.logs.fetchStorageHealth(assetId: asset.assetId);
      }
      if (!mounted) return;
      setState(() {
        _assets = assets;
        _healthByAsset
          ..clear()
          ..addAll(health);
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
        title: const Text('Storage Health'),
        actions: [IconButton(onPressed: _load, icon: const Icon(Icons.refresh))],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text(_error!))
              : ListView(
                  padding: const EdgeInsets.all(18),
                  children: [
                    Text('Storage health is fetched from the gateway Log HTTP API on port 7000.', style: Theme.of(context).textTheme.bodyMedium),
                    const SizedBox(height: 14),
                    ..._cards(),
                  ],
                ),
    );
  }

  List<Widget> _cards() {
    final assets = _assets?.assets ?? const <AssetModel>[];
    if (assets.isEmpty) return [const Text('No assets found.')];
    return assets.map((asset) {
      final h = _healthByAsset[asset.assetId] ?? const <String, dynamic>{};
      final status = h['status']?.toString() ?? 'unknown';
      return Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: StatusSummaryCard(
          title: '${asset.assetId} storage',
          status: status,
          icon: Icons.storage,
          subtitle: h['message']?.toString(),
          children: [
            KeyValueTable(
              values: h,
              preferredKeys: const [
                'base_path',
                'telemetry_dir_exists',
                'telemetry_files_count',
                'latest_telemetry_file',
                'disk_used_percent',
                'disk_free_bytes',
                'log_total_bytes',
              ],
              maxRows: 10,
            ),
          ],
        ),
      );
    }).toList(growable: false);
  }
}
