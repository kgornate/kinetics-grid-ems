import 'package:flutter/material.dart';

import '../features/assets/widgets/widgets.dart';
import '../models/models.dart';
import '../repositories/repositories.dart';
import 'asset_detail_screen.dart';

class AssetNavigationScreen extends StatefulWidget {
  final String gatewayIp;

  const AssetNavigationScreen({super.key, required this.gatewayIp});

  @override
  State<AssetNavigationScreen> createState() => _AssetNavigationScreenState();
}

class _AssetNavigationScreenState extends State<AssetNavigationScreen> {
  late final GatewayRepositoryBundle _repos = GatewayRepositoryBundle.forGateway(widget.gatewayIp);
  bool _loading = true;
  String? _error;
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
        _repos.assets.fetchAssets(),
        _repos.health.fetchAssetsHealth(),
      ]);
      if (!mounted) return;
      setState(() {
        _assets = results[0] as AssetListResponse;
        _health = results[1] as AssetsHealthResponse;
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

  void _openAsset(AssetModel asset) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => AssetDetailScreen(
          gatewayIp: widget.gatewayIp,
          asset: asset,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Assets'),
        actions: [IconButton(onPressed: _load, icon: const Icon(Icons.refresh))],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text(_error!))
              : ListView(
                  padding: const EdgeInsets.all(18),
                  children: [
                    DynamicAssetSummaryPanel(
                      assets: _assets,
                      health: _health,
                      loading: false,
                      error: null,
                      onRefresh: _load,
                      onOpenAsset: _openAsset,
                    ),
                  ],
                ),
    );
  }
}
