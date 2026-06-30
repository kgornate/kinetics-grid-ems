import 'package:flutter/material.dart';

import '../models/telemetry_signal.dart';
import '../utils/asset_field_strategy.dart';
import 'signal_metric_card.dart';

class AssetGroupSection extends StatelessWidget {
  const AssetGroupSection({
    super.key,
    required this.group,
    this.initiallyExpanded = false,
    this.onSignalTap,
  });

  final GroupedSignals group;
  final bool initiallyExpanded;
  final ValueChanged<TelemetrySignal>? onSignalTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ExpansionTile(
        initiallyExpanded: initiallyExpanded,
        leading: Icon(group.icon),
        title: Text(group.label),
        subtitle: Text('${group.signals.length} fields'),
        childrenPadding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
        children: [
          LayoutBuilder(
            builder: (context, constraints) {
              final width = constraints.maxWidth;
              final crossAxisCount = width > 1250 ? 4 : width > 900 ? 3 : width > 580 ? 2 : 1;
              return GridView.count(
                crossAxisCount: crossAxisCount,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                childAspectRatio: 2.05,
                children: [
                  for (final signal in group.signals.take(16))
                    InkWell(
                      onTap: onSignalTap == null ? null : () => onSignalTap!(signal),
                      child: SignalMetricCard(signal: signal, compact: true),
                    ),
                ],
              );
            },
          ),
          if (group.signals.length > 16)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text('${group.signals.length - 16} more fields available in table view.', style: Theme.of(context).textTheme.bodySmall),
            ),
        ],
      ),
    );
  }
}
