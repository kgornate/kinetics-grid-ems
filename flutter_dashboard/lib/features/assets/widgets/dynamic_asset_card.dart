import 'package:flutter/material.dart';

import '../../../models/models.dart';
import 'asset_health_chip.dart';
import 'asset_status_helpers.dart';

class DynamicAssetCard extends StatelessWidget {
  final AssetModel asset;
  final AssetHealthModel? health;
  final VoidCallback? onOpen;

  const DynamicAssetCard({
    super.key,
    required this.asset,
    this.health,
    this.onOpen,
  });

  @override
  Widget build(BuildContext context) {
    final status = health?.status ?? (asset.online ? 'healthy' : asset.runtimeMode);
    final subtitle = <String>[
      asset.assetType,
      if (asset.vendor != null && asset.vendor!.isNotEmpty) asset.vendor!,
      if (asset.protocol != null && asset.protocol!.isNotEmpty) asset.protocol!,
    ].join(' • ');

    return Card(
      elevation: 1,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  AssetStatusHelpers.iconForType(asset.assetType),
                  color: AssetStatusHelpers.statusColor(status, online: asset.online),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        asset.assetId,
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        subtitle.isEmpty ? asset.assetKey : subtitle,
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
                AssetHealthChip(status: status, online: asset.online),
              ],
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _miniChip('Mode', asset.runtimeMode),
                _miniChip('Running', asset.running ? 'yes' : 'no'),
                _miniChip('Enabled', asset.enabled ? 'yes' : 'no'),
                if (asset.telemetryAvailable) _miniChip('Telemetry', 'available'),
              ],
            ),
            if ((health?.recommendedAction ?? '').isNotEmpty) ...[
              const SizedBox(height: 10),
              Text(
                health!.recommendedAction!,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
            if (onOpen != null) ...[
              const SizedBox(height: 12),
              Align(
                alignment: Alignment.centerRight,
                child: OutlinedButton.icon(
                  onPressed: onOpen,
                  icon: const Icon(Icons.open_in_new),
                  label: const Text('Open'),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _miniChip(String label, String value) {
    return Chip(
      visualDensity: VisualDensity.compact,
      label: Text('$label: ${AssetStatusHelpers.titleCase(value)}'),
    );
  }
}
