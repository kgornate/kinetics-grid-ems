import 'package:flutter/material.dart';

import '../models/asset_summary.dart';
import '../models/signal_preview.dart';

class AssetCard extends StatelessWidget {
  const AssetCard({
    super.key,
    required this.asset,
    required this.onTap,
    this.previewSignals = const [],
  });

  final AssetSummary asset;
  final VoidCallback onTap;
  final List<SignalPreview> previewSignals;

  @override
  Widget build(BuildContext context) {
    final preview = previewSignals.take(4).toList();
    final statusColor = asset.online ? Colors.green : Colors.red;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(height: 4, color: statusColor),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        CircleAvatar(
                          radius: 16,
                          backgroundColor: statusColor.withOpacity(0.14),
                          foregroundColor: statusColor,
                          child: Icon(_assetIcon(asset.assetId), size: 18),
                        ),
                        const SizedBox(width: 9),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(asset.displayName, style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700), overflow: TextOverflow.ellipsis),
                              Text(asset.assetType == null ? asset.assetId : '${asset.assetId} - ${asset.assetType}', style: Theme.of(context).textTheme.bodySmall, overflow: TextOverflow.ellipsis),
                            ],
                          ),
                        ),
                        Icon(Icons.chevron_right, color: Theme.of(context).hintColor),
                      ],
                    ),
                    const SizedBox(height: 12),
                    if (preview.isEmpty)
                      Expanded(child: Center(child: Text('No key signals yet', style: Theme.of(context).textTheme.bodySmall)))
                    else
                      Expanded(
                        child: Column(
                          children: [
                            for (final signal in preview)
                              Padding(
                                padding: const EdgeInsets.only(bottom: 7),
                                child: _PreviewRow(signal: signal),
                              ),
                          ],
                        ),
                      ),
                    const Divider(height: 14),
                    Wrap(
                      spacing: 8,
                      runSpacing: 4,
                      children: [
                        _MiniBadge(label: 'Signals ${asset.signalCount}'),
                        _MiniBadge(label: 'Bad ${asset.badSignalCount}', isWarning: asset.badSignalCount > 0),
                        if (asset.sourceId != null) _MiniBadge(label: asset.sourceId!),
                        if (asset.lastUpdateUtc != null) _MiniBadge(label: 'Updated ${_shortTime(asset.lastUpdateUtc!)}'),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  static IconData _assetIcon(String assetId) {
    final id = assetId.toLowerCase();
    if (id.contains('bms')) return Icons.battery_charging_full;
    if (id.contains('pcs')) return Icons.electrical_services;
    if (id.contains('meter')) return Icons.speed;
    if (id.contains('fire')) return Icons.local_fire_department;
    if (id.contains('cooling')) return Icons.ac_unit;
    if (id.contains('dehumid')) return Icons.water_drop;
    if (id.contains('io')) return Icons.input;
    if (id.contains('remote')) return Icons.settings_remote;
    return Icons.hub;
  }

  static String _shortTime(String value) {
    if (value.length <= 19) return value;
    return value.substring(0, 19).replaceFirst('T', ' ');
  }
}

class _PreviewRow extends StatelessWidget {
  const _PreviewRow({required this.signal});

  final SignalPreview signal;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Text(signal.displayName, overflow: TextOverflow.ellipsis, style: Theme.of(context).textTheme.bodySmall),
        ),
        const SizedBox(width: 8),
        Flexible(
          child: Text(
            signal.valueText,
            textAlign: TextAlign.right,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w700),
          ),
        ),
      ],
    );
  }
}

class _MiniBadge extends StatelessWidget {
  const _MiniBadge({required this.label, this.isWarning = false});

  final String label;
  final bool isWarning;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(999),
        color: isWarning ? Colors.orange.withOpacity(0.15) : Theme.of(context).colorScheme.surfaceVariant,
      ),
      child: Text(label, style: Theme.of(context).textTheme.labelSmall),
    );
  }
}
