import 'package:flutter/material.dart';

import '../../../models/models.dart';
import 'asset_status_helpers.dart';
import 'dynamic_asset_card.dart';

class DynamicAssetSummaryPanel extends StatelessWidget {
  final AssetListResponse? assets;
  final AssetsHealthResponse? health;
  final bool loading;
  final String? error;
  final VoidCallback onRefresh;
  final ValueChanged<AssetModel>? onOpenAsset;

  const DynamicAssetSummaryPanel({
    super.key,
    required this.assets,
    required this.health,
    required this.loading,
    required this.error,
    required this.onRefresh,
    this.onOpenAsset,
  });

  @override
  Widget build(BuildContext context) {
    final assetList = assets?.assets ?? const <AssetModel>[];

    return Card(
      elevation: 1,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.dashboard_customize),
                const SizedBox(width: 10),
                const Expanded(
                  child: Text(
                    'Dynamic Asset Runtime',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
                  ),
                ),
                if (loading)
                  const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                else
                  IconButton(
                    tooltip: 'Refresh assets and health',
                    onPressed: onRefresh,
                    icon: const Icon(Icons.refresh),
                  ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              'Backend asset catalog + health view. Existing fixed cards remain below for compatibility.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 12),
            if (error != null && error!.isNotEmpty)
              _errorBox(context, error!)
            else if (assetList.isEmpty && !loading)
              const Text('No asset catalog received yet. Click refresh or check Web API connection.')
            else ...[
              _summaryRow(context, assetList),
              const SizedBox(height: 12),
              LayoutBuilder(
                builder: (context, constraints) {
                  // Use a wrapping layout instead of a fixed-height grid.
                  // Asset cards may include health recommendations, command state,
                  // or longer labels; fixed grid heights can overflow on Windows.
                  final useTwoColumns = constraints.maxWidth > 900;
                  final cardWidth = useTwoColumns
                      ? (constraints.maxWidth - 12) / 2
                      : constraints.maxWidth;

                  return Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    children: assetList.map((asset) {
                      return SizedBox(
                        width: cardWidth,
                        child: DynamicAssetCard(
                          asset: asset,
                          health: health?.assets[asset.assetId] ?? health?.assets[asset.assetKey],
                          onOpen: onOpenAsset == null ? null : () => onOpenAsset!(asset),
                        ),
                      );
                    }).toList(),
                  );
                },
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _summaryRow(BuildContext context, List<AssetModel> assetList) {
    final running = assetList.where((a) => a.running).length;
    final online = assetList.where((a) => a.online).length;
    final disabled = assetList.where((a) => a.isDisabled).length;
    return Wrap(
      spacing: 10,
      runSpacing: 8,
      children: [
        _summaryChip('Total', assetList.length.toString(), Colors.blueGrey),
        _summaryChip('Running', running.toString(), Colors.green),
        _summaryChip('Online', online.toString(), Colors.green),
        _summaryChip('Disabled', disabled.toString(), Colors.grey),
        if (health != null)
          _summaryChip(
            'Health',
            health!.status,
            AssetStatusHelpers.statusColor(health!.status),
          ),
      ],
    );
  }

  Widget _summaryChip(String label, String value, Color color) {
    return Chip(
      avatar: Icon(Icons.circle, size: 12, color: color),
      label: Text('$label: ${AssetStatusHelpers.titleCase(value)}'),
      side: BorderSide(color: color.withOpacity(0.4)),
    );
  }

  Widget _errorBox(BuildContext context, String message) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.red.withOpacity(0.08),
        border: Border.all(color: Colors.red.withOpacity(0.35)),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(
        message,
        style: TextStyle(color: Colors.red.shade800),
      ),
    );
  }
}
