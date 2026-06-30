import 'package:flutter/material.dart';

import '../models/telemetry_signal.dart';

class SignalTile extends StatelessWidget {
  const SignalTile({super.key, required this.signal});

  final TelemetrySignal signal;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        dense: true,
        title: Text(signal.displayName),
        subtitle: Text('${signal.name} - ${signal.category} - quality=${signal.quality}'),
        trailing: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 220),
          child: Text(
            signal.valueText,
            textAlign: TextAlign.right,
            style: Theme.of(context).textTheme.titleMedium,
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ),
    );
  }
}
