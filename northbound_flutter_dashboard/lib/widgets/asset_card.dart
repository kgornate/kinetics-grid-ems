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
    return Card(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(asset.online ? Icons.check_circle : Icons.cancel, color: asset.online ? Colors.green : Colors.red),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(asset.displayName, style: Theme.of(context).textTheme.titleMedium, overflow: TextOverflow.ellipsis),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Text(
                asset.assetType == null ? asset.assetId : '${asset.assetId} - ${asset.assetType}',
                style: Theme.of(context).textTheme.bodySmall,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 10),
              if (preview.isEmpty)
                Expanded(child: Center(child: Text('No key signals yet', style: Theme.of(context).textTheme.bodySmall)))
              else
                Expanded(
                  child: Column(
                    children: [
                      for (final signal in preview)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 5),
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
                  if (asset.lastUpdateUtc != null) _MiniBadge(label: 'Updated ${_shortTime(asset.lastUpdateUtc!)}'),
                ],
              ),
            ],
          ),
        ),
      ),
    );
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
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
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
