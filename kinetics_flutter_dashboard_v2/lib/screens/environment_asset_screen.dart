import 'package:flutter/material.dart';

import '../core/presentation/telemetry_presentation.dart';
import '../models/gateway_models.dart';
import '../widgets/common_widgets.dart';

class EnvironmentAssetScreen extends StatelessWidget {
  const EnvironmentAssetScreen({super.key, required this.asset});

  final AssetSnapshot asset;

  @override
  Widget build(BuildContext context) {
    final sections = _sections(asset);
    return Scaffold(
      appBar: AppBar(
        title: Text(assetTitle(asset)),
        actions: [
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 10),
            child: StatusPill(label: asset.online ? 'Online' : 'Offline', good: asset.online),
          ),
          const SizedBox(width: 12),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          SectionHeader(
            assetTitle(asset),
            subtitle: '${asset.telemetry.length} mapped points • ${asset.timestamp == null ? 'No timestamp' : shortTime(asset.timestamp!)}',
          ),
          const SizedBox(height: 16),
          MetricGrid(children: _summaryCards(asset)),
          const SizedBox(height: 22),
          ...sections.entries.map((section) => TelemetrySection(
                title: section.key,
                asset: asset,
                entries: section.value,
                initiallyExpanded: true,
              )),
          const SizedBox(height: 14),
          Card(
            clipBehavior: Clip.antiAlias,
            child: ExpansionTile(
              title: const Text('All asset points', style: TextStyle(fontWeight: FontWeight.w800)),
              subtitle: const Text('Search raw keys, decoded values and register addresses'),
              childrenPadding: const EdgeInsets.fromLTRB(12, 8, 12, 16),
              children: [EngineeringTable(asset: asset, maxHeight: 620)],
            ),
          ),
          const SizedBox(height: 40),
        ],
      ),
    );
  }

  List<Widget> _summaryCards(AssetSnapshot asset) {
    switch (asset.assetType) {
      case 'hvac':
        return [
          _metric('aircond_1_1', 'Unit status', Icons.power),
          _metric('aircond_1_10', 'Indoor temperature', Icons.thermostat, emphasis: true),
          _metric('aircond_1_11', 'Humidity', Icons.water_drop, emphasis: true),
          _metric('aircond_1_4', 'Compressor', Icons.settings),
          _metric('aircond_1_2', 'Indoor fan', Icons.air),
          _metric('aircond_1_14', 'AC input voltage', Icons.bolt),
        ];
      case 'liquid_cooling':
        return [
          _metric('liquidcool_1_12', 'Unit status', Icons.power),
          _metric('liquidcool_1_6', 'Outlet temperature', Icons.thermostat, emphasis: true),
          _metric('liquidcool_1_7', 'Return temperature', Icons.device_thermostat, emphasis: true),
          _metric('liquidcool_1_1', 'Pump speed', Icons.speed),
          _metric('liquidcool_1_8', 'Outlet pressure', Icons.speed),
          _metric('liquidcool_1_19', 'Alarm level', Icons.warning_amber),
        ];
      case 'energy_meter':
        return [
          _metric('essmeter_1_29', 'Average line voltage', Icons.bolt, emphasis: true),
          _metric('essmeter_1_30', 'Average current', Icons.electric_meter, emphasis: true),
          _metric('essmeter_1_14', 'Total active power', Icons.power, emphasis: true),
          _metric('essmeter_1_18', 'Total reactive power', Icons.swap_horiz),
          _metric('essmeter_1_26', 'Power factor', Icons.speed),
          _metric('essmeter_1_27', 'Frequency', Icons.show_chart),
        ];
      case 'dehumidifier_1':
      case 'dehumidifier_2':
        return [
          _metric(asset.assetId == 'dehumidifier_1' ? 'dehumidifier_1' : 'dehumidifier2_1', 'Operating status', Icons.power),
          _metric(asset.assetId == 'dehumidifier_1' ? 'dehumidifier_4' : 'dehumidifier2_4', 'Humidity', Icons.water_drop, emphasis: true),
          _metric(asset.assetId == 'dehumidifier_1' ? 'dehumidifier_3' : 'dehumidifier2_3', 'Dew point', Icons.device_thermostat, emphasis: true),
          _metric(asset.assetId == 'dehumidifier_1' ? 'dehumidifier_2' : 'dehumidifier2_2', 'Alarm status', Icons.warning_amber),
        ];
      case 'safety_io':
        return [
          _metric('di1h', 'Emergency stop', Icons.report_problem, emphasis: true),
          _metric('di6h', 'Fire alarm level 1', Icons.local_fire_department),
          _metric('di4h', 'Fire alarm level 2', Icons.local_fire_department),
          _metric('di5h', 'Fire-system fault', Icons.warning),
          _metric('di8l', 'Electrical water leak', Icons.water_drop),
          _metric('di10l', 'Battery water leak', Icons.water_drop),
        ];
      default:
        return asset.telemetry.entries.take(6).map((entry) {
          final shown = presentPoint(asset.assetType, entry.key, entry.value);
          return MetricTile(label: friendlyName(entry.key, entry.value), value: shown.text, subtitle: shown.note, icon: Icons.memory);
        }).toList();
    }
  }

  Widget _metric(String key, String label, IconData icon, {bool emphasis = false}) {
    final point = asset.telemetry[key];
    final shown = point == null
        ? const PresentedValue(value: '--', unit: '', valid: false)
        : presentPoint(asset.assetType, key, point);
    return MetricTile(label: label, value: shown.text, subtitle: shown.note, icon: icon, emphasis: emphasis);
  }

  Map<String, List<MapEntry<String, TelemetryPoint>>> _sections(AssetSnapshot asset) {
    switch (asset.assetType) {
      case 'hvac':
        return <String, List<MapEntry<String, TelemetryPoint>>>{
          'Operating state': entriesForKeys(asset, const ['hvac_comm_fault', 'aircond_1_1', 'aircond_1_2', 'aircond_1_3', 'aircond_1_4', 'aircond_1_5', 'aircond_1_59']),
          'Temperature and humidity': entriesForKeys(asset, const ['aircond_1_7', 'aircond_1_9', 'aircond_1_10', 'aircond_1_11']),
          'Electrical': entriesForKeys(asset, const ['aircond_1_14', 'aircond_1_41', 'aircond_1_42']),
          'Alarms and sensor faults': entriesWhere(asset, (key, point) {
            final lower = '${key}_${point.nameEn ?? ''}'.toLowerCase();
            return lower.contains('alarm') || lower.contains('fault') || lower.contains('lockout') || lower.contains('anti-freeze');
          }),
          'Setpoints and commands': entriesWhere(asset, (key, point) => key.compareTo('aircond_1_49') >= 0),
        };
      case 'liquid_cooling':
        return <String, List<MapEntry<String, TelemetryPoint>>>{
          'Operating state': entriesForKeys(asset, const ['liquid_cooling_comm_fault', 'liquidcool_1_1', 'liquidcool_1_2', 'liquidcool_1_3', 'liquidcool_1_4', 'liquidcool_1_5', 'liquidcool_1_12', 'liquidcool_1_13']),
          'Cooling circuit': entriesForKeys(asset, const ['liquidcool_1_6', 'liquidcool_1_7', 'liquidcool_1_8', 'liquidcool_1_9', 'liquidcool_1_10', 'liquidcool_1_11']),
          'Alarms': entriesWhere(asset, (key, point) => key.contains('alarm') || (point.nameEn ?? '').toLowerCase().contains('alarm')),
          'Setpoints and controls': entriesWhere(asset, (key, point) {
            final number = int.tryParse(key.split('_').last);
            return number != null && number >= 20;
          }),
        };
      case 'energy_meter':
        return <String, List<MapEntry<String, TelemetryPoint>>>{
          'Voltage': entriesForKeys(asset, const ['essmeter_1_1', 'essmeter_1_2', 'essmeter_1_3', 'essmeter_1_4', 'essmeter_1_5', 'essmeter_1_6', 'essmeter_1_28', 'essmeter_1_29']),
          'Current': entriesForKeys(asset, const ['essmeter_1_7', 'essmeter_1_8', 'essmeter_1_9', 'essmeter_1_10', 'essmeter_1_30']),
          'Active power': entriesForKeys(asset, const ['essmeter_1_11', 'essmeter_1_12', 'essmeter_1_13', 'essmeter_1_14']),
          'Reactive power': entriesForKeys(asset, const ['essmeter_1_15', 'essmeter_1_16', 'essmeter_1_17', 'essmeter_1_18']),
          'Apparent power': entriesForKeys(asset, const ['essmeter_1_19', 'essmeter_1_20', 'essmeter_1_21', 'essmeter_1_22']),
          'Power factor and frequency': entriesForKeys(asset, const ['essmeter_1_23', 'essmeter_1_24', 'essmeter_1_25', 'essmeter_1_26', 'essmeter_1_27']),
          'Communication': entriesForKeys(asset, const ['energy_meter_comm_fault']),
        };
      case 'dehumidifier_1':
      case 'dehumidifier_2':
        return <String, List<MapEntry<String, TelemetryPoint>>>{
          'Operating state': entriesWhere(asset, (key, point) => key.endsWith('_1') || key.endsWith('_2')),
          'Environmental measurements': entriesWhere(asset, (key, point) => !key.endsWith('_1') && !key.endsWith('_2')),
        };
      case 'safety_io':
        return <String, List<MapEntry<String, TelemetryPoint>>>{
          'Emergency, fire and access': entriesForKeys(asset, const ['di1h', 'di2h', 'di4h', 'di5h', 'di6h', 'di7l', 'di13h']),
          'Water, breaker and electrical protection': entriesForKeys(asset, const ['di8l', 'di10l', 'di11l', 'di12l', 'di14l']),
          'Digital outputs': entriesForKeys(asset, const ['do1', 'do2', 'do3', 'do4']),
        };
      default:
        return <String, List<MapEntry<String, TelemetryPoint>>>{'Telemetry': asset.telemetry.entries.toList()};
    }
  }
}
