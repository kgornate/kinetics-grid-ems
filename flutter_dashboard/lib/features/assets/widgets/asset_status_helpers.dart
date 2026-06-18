import 'package:flutter/material.dart';

class AssetStatusHelpers {
  const AssetStatusHelpers._();

  static Color statusColor(String status, {bool online = false}) {
    final text = status.toLowerCase();
    if (text == 'healthy' || online) return Colors.green;
    if (text == 'degraded' || text == 'warning') return Colors.orange;
    if (text == 'offline' || text == 'error' || text == 'failed') return Colors.red;
    if (text == 'disabled') return Colors.grey;
    return Colors.blueGrey;
  }

  static IconData iconForType(String assetType) {
    final type = assetType.toLowerCase();
    if (type.contains('bms') || type.contains('battery')) return Icons.battery_charging_full;
    if (type.contains('pcs') || type.contains('inverter')) return Icons.electrical_services;
    if (type.contains('chiller') || type.contains('hvac')) return Icons.ac_unit;
    if (type.contains('meter')) return Icons.speed;
    return Icons.memory;
  }

  static String titleCase(String value) {
    if (value.isEmpty) return '--';
    return value
        .split('_')
        .where((part) => part.isNotEmpty)
        .map((part) => part[0].toUpperCase() + part.substring(1))
        .join(' ');
  }
}
