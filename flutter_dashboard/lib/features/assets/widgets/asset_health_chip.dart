import 'package:flutter/material.dart';

import 'asset_status_helpers.dart';

class AssetHealthChip extends StatelessWidget {
  final String status;
  final bool online;

  const AssetHealthChip({
    super.key,
    required this.status,
    this.online = false,
  });

  @override
  Widget build(BuildContext context) {
    final color = AssetStatusHelpers.statusColor(status, online: online);
    final label = status.isEmpty ? (online ? 'online' : 'unknown') : status;
    return Chip(
      visualDensity: VisualDensity.compact,
      avatar: Icon(Icons.circle, size: 12, color: color),
      label: Text(AssetStatusHelpers.titleCase(label)),
      side: BorderSide(color: color.withOpacity(0.4)),
    );
  }
}
