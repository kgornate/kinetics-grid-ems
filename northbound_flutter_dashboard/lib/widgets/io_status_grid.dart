import 'package:flutter/material.dart';

import '../models/telemetry_signal.dart';

class IoStatusGrid extends StatelessWidget {
  const IoStatusGrid({super.key, required this.signals});

  final List<TelemetrySignal> signals;

  @override
  Widget build(BuildContext context) {
    if (signals.isEmpty) return const SizedBox.shrink();
    return LayoutBuilder(
      builder: (context, constraints) {
        final crossAxisCount = constraints.maxWidth > 1100 ? 4 : constraints.maxWidth > 720 ? 3 : constraints.maxWidth > 460 ? 2 : 1;
        return GridView.count(
          crossAxisCount: crossAxisCount,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          childAspectRatio: 3.4,
          children: [for (final signal in signals) _IoTile(signal: signal)],
        );
      },
    );
  }
}

class _IoTile extends StatelessWidget {
  const _IoTile({required this.signal});

  final TelemetrySignal signal;

  @override
  Widget build(BuildContext context) {
    final isNormal = signal.isGood && !_looksActiveFault(signal);
    final color = isNormal ? Colors.green : Colors.orange;
    return Card(
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: color.withOpacity(0.13),
          foregroundColor: color,
          child: Icon(isNormal ? Icons.check_circle : Icons.warning_amber),
        ),
        title: Text(signal.displayName, maxLines: 1, overflow: TextOverflow.ellipsis),
        subtitle: Text(signal.name, maxLines: 1, overflow: TextOverflow.ellipsis),
        trailing: Text(signal.valueText, style: const TextStyle(fontWeight: FontWeight.w700)),
      ),
    );
  }

  bool _looksActiveFault(TelemetrySignal signal) {
    final text = '${signal.displayName} ${signal.name} ${signal.valueText}'.toLowerCase();
    if (!(text.contains('fault') || text.contains('alarm') || text.contains('emergency') || text.contains('stop'))) return false;
    final value = signal.value;
    if (value is num) return value != 0;
    return text.contains('active') || text.contains('fault') || text.contains('alarm');
  }
}
