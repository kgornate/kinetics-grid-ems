import 'package:flutter/material.dart';

import '../core/presentation/telemetry_presentation.dart';
import '../models/gateway_models.dart';
import '../widgets/common_widgets.dart';

class AssetTelemetryScreen extends StatelessWidget {
  const AssetTelemetryScreen({
    super.key,
    required this.asset,
    this.title,
    this.onRefresh,
    this.refreshLabel = 'Refresh',
  });

  final AssetSnapshot asset;
  final String? title;
  final Future<void> Function()? onRefresh;
  final String refreshLabel;

  @override
  Widget build(BuildContext context) {
    final grouped = <String, List<MapEntry<String, TelemetryPoint>>>{};
    for (final entry in asset.telemetry.entries) {
      grouped.putIfAbsent(categoryTitle(entry.key, entry.value), () => []).add(entry);
    }
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        SectionHeader(
          title ?? assetTitle(asset),
          subtitle: '${asset.telemetry.length} points • ${asset.online ? 'Online' : 'Offline'} • ${asset.timestamp ?? 'No timestamp'}',
          trailing: onRefresh == null
              ? null
              : FilledButton.tonalIcon(
                  onPressed: () async => onRefresh!(),
                  icon: const Icon(Icons.refresh),
                  label: Text(refreshLabel),
                ),
        ),
        const SizedBox(height: 16),
        ...grouped.entries.map((group) => TelemetrySection(
              title: group.key,
              asset: asset,
              entries: group.value,
              initiallyExpanded: group.key != 'Configuration and thresholds',
            )),
        const SizedBox(height: 16),
        Card(
          clipBehavior: Clip.antiAlias,
          child: ExpansionTile(
            title: const Text('All signals', style: TextStyle(fontWeight: FontWeight.w800)),
            childrenPadding: const EdgeInsets.fromLTRB(12, 8, 12, 16),
            children: [EngineeringTable(asset: asset, maxHeight: 620)],
          ),
        ),
        const SizedBox(height: 40),
      ],
    );
  }
}
