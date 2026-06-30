import 'package:flutter/material.dart';

import '../models/telemetry_signal.dart';
import '../utils/value_formatters.dart';

class SignalMetricCard extends StatelessWidget {
  const SignalMetricCard({super.key, required this.signal, this.compact = false});

  final TelemetrySignal signal;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final color = signal.isGood ? Theme.of(context).colorScheme.primary : Colors.orange;
    return Card(
      child: Padding(
        padding: EdgeInsets.all(compact ? 10 : 14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(
                  radius: compact ? 14 : 17,
                  backgroundColor: color.withOpacity(0.13),
                  foregroundColor: color,
                  child: Icon(_iconFor(signal.category), size: compact ? 16 : 18),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    signal.displayName,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.labelLarge,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Text(
              signal.valueText,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
            ),
            const Spacer(),
            Wrap(
              spacing: 6,
              runSpacing: 4,
              children: [
                Chip(label: Text(signal.category), visualDensity: VisualDensity.compact),
                Chip(label: Text(signal.quality), visualDensity: VisualDensity.compact),
                if (signal.address != null) Chip(label: Text('0x${signal.address!.toRadixString(16).toUpperCase()}'), visualDensity: VisualDensity.compact),
              ],
            ),
            if (!compact) ...[
              const SizedBox(height: 6),
              Text('Updated ${ValueFormatters.compactDateTime(signal.timestampUtc)}', style: Theme.of(context).textTheme.bodySmall, overflow: TextOverflow.ellipsis),
            ],
          ],
        ),
      ),
    );
  }

  IconData _iconFor(String category) {
    final c = category.toLowerCase();
    if (c.contains('soc')) return Icons.battery_5_bar;
    if (c.contains('power')) return Icons.bolt;
    if (c.contains('voltage')) return Icons.electrical_services;
    if (c.contains('current')) return Icons.timeline;
    if (c.contains('thermal') || c.contains('temp')) return Icons.thermostat;
    if (c.contains('alarm') || c.contains('fault')) return Icons.warning_amber;
    if (c.contains('status')) return Icons.info_outline;
    if (c.contains('insulation')) return Icons.shield;
    return Icons.sensors;
  }
}
