import 'dart:convert';

import 'package:flutter/material.dart';

import '../core/presentation/telemetry_presentation.dart';
import '../models/gateway_models.dart';

class StatusPill extends StatelessWidget {
  const StatusPill({
    super.key,
    required this.label,
    required this.good,
    this.icon,
  });

  final String label;
  final bool good;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final foreground = good ? colors.primary : colors.error;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: foreground.withOpacity(0.10),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: foreground.withOpacity(0.35)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon ?? (good ? Icons.check_circle : Icons.error), size: 16, color: foreground),
          const SizedBox(width: 6),
          Text(label, style: TextStyle(color: foreground, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}

class MetricTile extends StatelessWidget {
  const MetricTile({
    super.key,
    required this.label,
    required this.value,
    this.icon,
    this.subtitle,
    this.emphasis = false,
  });

  final String label;
  final String value;
  final IconData? icon;
  final String? subtitle;
  final bool emphasis;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Card(
      elevation: emphasis ? 1 : 0,
      color: emphasis ? colors.primaryContainer.withOpacity(0.42) : null,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            if (icon != null) ...[
              CircleAvatar(
                backgroundColor: colors.primaryContainer,
                foregroundColor: colors.onPrimaryContainer,
                child: Icon(icon),
              ),
              const SizedBox(width: 12),
            ],
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(label, style: Theme.of(context).textTheme.labelLarge),
                  const SizedBox(height: 4),
                  Text(
                    value,
                    style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  if (subtitle != null && subtitle!.isNotEmpty) ...[
                    const SizedBox(height: 3),
                    Text(subtitle!, style: Theme.of(context).textTheme.bodySmall, maxLines: 2, overflow: TextOverflow.ellipsis),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class MetricGrid extends StatelessWidget {
  const MetricGrid({super.key, required this.children, this.minWidth = 220});

  final List<Widget> children;
  final double minWidth;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final count = (constraints.maxWidth / minWidth).floor().clamp(1, 6).toInt();
        return GridView.count(
          crossAxisCount: count,
          childAspectRatio: 1.65,
          crossAxisSpacing: 12,
          mainAxisSpacing: 12,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          children: children,
        );
      },
    );
  }
}

class RichAssetCard extends StatelessWidget {
  const RichAssetCard({
    super.key,
    required this.asset,
    required this.metrics,
    this.onTap,
    this.title,
    this.warningCount = 0,
  });

  final AssetSnapshot asset;
  final List<String> metrics;
  final VoidCallback? onTap;
  final String? title;
  final int warningCount;

  @override
  Widget build(BuildContext context) {
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(iconForAsset(asset.assetType)),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      title ?? assetTitle(asset),
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800),
                    ),
                  ),
                  StatusPill(label: asset.online ? 'Online' : 'Offline', good: asset.online),
                ],
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: metrics
                    .where((metric) => metric.trim().isNotEmpty)
                    .map((metric) => Container(
                          padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
                          decoration: BoxDecoration(
                            color: Theme.of(context).colorScheme.surfaceContainerHighest.withOpacity(0.7),
                            borderRadius: BorderRadius.circular(9),
                          ),
                          child: Text(metric, style: Theme.of(context).textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600)),
                        ))
                    .toList(),
              ),
              const Spacer(),
              Row(
                children: [
                  if (warningCount > 0) ...[
                    Icon(Icons.warning_amber, size: 16, color: Theme.of(context).colorScheme.error),
                    const SizedBox(width: 4),
                    Text('$warningCount active', style: TextStyle(color: Theme.of(context).colorScheme.error, fontWeight: FontWeight.w700)),
                    const Spacer(),
                  ],
                  Text(
                    asset.timestamp == null ? 'No update received' : 'Updated ${shortTime(asset.timestamp!)}',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class AssetCard extends StatelessWidget {
  const AssetCard({
    super.key,
    required this.asset,
    this.onTap,
    this.subtitle,
  });

  final AssetSnapshot asset;
  final VoidCallback? onTap;
  final String? subtitle;

  @override
  Widget build(BuildContext context) {
    return RichAssetCard(asset: asset, onTap: onTap, metrics: [if (subtitle != null) subtitle!]);
  }
}

class EngineeringTable extends StatefulWidget {
  const EngineeringTable({
    super.key,
    required this.asset,
    this.entries,
    this.compact = false,
    this.showSearch = true,
    this.maxHeight,
  });

  final AssetSnapshot asset;
  final List<MapEntry<String, TelemetryPoint>>? entries;
  final bool compact;
  final bool showSearch;
  final double? maxHeight;

  @override
  State<EngineeringTable> createState() => _EngineeringTableState();
}

class _EngineeringTableState extends State<EngineeringTable> {
  final TextEditingController _search = TextEditingController();
  bool _goodOnly = false;

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final query = _search.text.toLowerCase().trim();
    final source = widget.entries ?? widget.asset.telemetry.entries.toList();
    final entries = source.where((entry) {
      if (_goodOnly && !entry.value.isGood) return false;
      if (query.isEmpty) return true;
      final name = friendlyName(entry.key, entry.value).toLowerCase();
      final presented = presentPoint(widget.asset.assetType, entry.key, entry.value).text.toLowerCase();
      return entry.key.toLowerCase().contains(query) || name.contains(query) || presented.contains(query);
    }).toList();

    final table = Card(
      clipBehavior: Clip.antiAlias,
      child: ListView.separated(
        shrinkWrap: widget.maxHeight == null,
        physics: widget.maxHeight == null ? const NeverScrollableScrollPhysics() : null,
        itemCount: entries.length,
        separatorBuilder: (_, __) => const Divider(height: 1),
        itemBuilder: (context, index) {
          final entry = entries[index];
          final point = entry.value;
          final presented = presentPoint(widget.asset.assetType, entry.key, point);
          return ListTile(
            dense: widget.compact,
            title: Text(friendlyName(entry.key, point), style: const TextStyle(fontWeight: FontWeight.w600)),
            subtitle: Text([
              entry.key,
              if (point.address != null) point.address!,
              if (point.access != null) point.access!,
            ].join('  •  ')),
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 260),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Text(
                        presented.text,
                        textAlign: TextAlign.end,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontWeight: FontWeight.w800),
                      ),
                      if (presented.note != null)
                        Text(presented.note!, style: Theme.of(context).textTheme.bodySmall, overflow: TextOverflow.ellipsis),
                    ],
                  ),
                ),
                const SizedBox(width: 10),
                Icon(
                  point.isGood && presented.valid ? Icons.check_circle : Icons.warning_amber,
                  size: 18,
                  color: point.isGood && presented.valid
                      ? Theme.of(context).colorScheme.primary
                      : Theme.of(context).colorScheme.error,
                ),
              ],
            ),
            onTap: () => _showPoint(context, entry.key, point),
          );
        },
      ),
    );

    return Column(
      children: [
        if (widget.showSearch) ...[
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _search,
                  onChanged: (_) => setState(() {}),
                  decoration: const InputDecoration(
                    prefixIcon: Icon(Icons.search),
                    labelText: 'Search by name, key or value',
                    border: OutlineInputBorder(),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              FilterChip(
                label: const Text('Good quality only'),
                selected: _goodOnly,
                onSelected: (value) => setState(() => _goodOnly = value),
              ),
            ],
          ),
          const SizedBox(height: 12),
        ],
        if (widget.maxHeight == null) table else SizedBox(height: widget.maxHeight, child: table),
      ],
    );
  }

  void _showPoint(BuildContext context, String key, TelemetryPoint point) {
    final pretty = const JsonEncoder.withIndent('  ').convert(point.toJson());
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(friendlyName(key, point)),
        content: SizedBox(width: 720, child: SingleChildScrollView(child: SelectableText(pretty))),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
      ),
    );
  }
}

class TelemetryTable extends StatelessWidget {
  const TelemetryTable({super.key, required this.asset, this.initialQuery = ''});

  final AssetSnapshot asset;
  final String initialQuery;

  @override
  Widget build(BuildContext context) => EngineeringTable(asset: asset, maxHeight: 620);
}

class TelemetrySection extends StatelessWidget {
  const TelemetrySection({
    super.key,
    required this.title,
    required this.asset,
    required this.entries,
    this.subtitle,
    this.initiallyExpanded = true,
  });

  final String title;
  final String? subtitle;
  final AssetSnapshot asset;
  final List<MapEntry<String, TelemetryPoint>> entries;
  final bool initiallyExpanded;

  @override
  Widget build(BuildContext context) {
    if (entries.isEmpty) return const SizedBox.shrink();
    return Card(
      child: ExpansionTile(
        initiallyExpanded: initiallyExpanded,
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
        subtitle: subtitle == null ? Text('${entries.length} signals') : Text(subtitle!),
        childrenPadding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
        children: [EngineeringTable(asset: asset, entries: entries, compact: true, showSearch: false)],
      ),
    );
  }
}

class SectionHeader extends StatelessWidget {
  const SectionHeader(this.title, {super.key, this.subtitle, this.trailing});

  final String title;
  final String? subtitle;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800)),
              if (subtitle != null) ...[
                const SizedBox(height: 4),
                Text(subtitle!, style: Theme.of(context).textTheme.bodyMedium),
              ],
            ],
          ),
        ),
        if (trailing != null) trailing!,
      ],
    );
  }
}

IconData iconForAsset(String type) {
  switch (type) {
    case 'bms_bank':
      return Icons.battery_charging_full;
    case 'bms_rack':
      return Icons.view_column;
    case 'pcs':
      return Icons.electrical_services;
    case 'hvac':
      return Icons.ac_unit;
    case 'liquid_cooling':
      return Icons.water_drop;
    case 'energy_meter':
      return Icons.speed;
    case 'safety_io':
      return Icons.health_and_safety;
    default:
      return Icons.memory;
  }
}

String assetTitle(AssetSnapshot asset) {
  if (asset.label != null && asset.label!.trim().isNotEmpty) {
    return asset.label!.trim();
  }
  if (asset.rackId != null) return 'Rack ${asset.rackId} / BCU ${asset.rackId}';
  if (asset.assetType == 'pcs') return 'PCS ${asset.unitId ?? asset.assetId.replaceAll('pcs_', '')}';
  const names = <String, String>{
    'bms_bank': 'BMS Bank / BAU',
    'hvac': 'HVAC',
    'liquid_cooling': 'Liquid cooling',
    'energy_meter': 'Energy meter',
    'dehumidifier_1': 'Dehumidifier 1',
    'dehumidifier_2': 'Dehumidifier 2',
    'safety_io': 'Safety and fire I/O',
    'environment_other': 'Other environment',
  };
  return names[asset.assetId] ?? prettifyKey(asset.assetId);
}

String shortTime(String timestamp) {
  final parsed = DateTime.tryParse(timestamp)?.toLocal();
  if (parsed == null) return timestamp;
  String two(int value) => value.toString().padLeft(2, '0');
  return '${two(parsed.day)}/${two(parsed.month)} ${two(parsed.hour)}:${two(parsed.minute)}:${two(parsed.second)}';
}
