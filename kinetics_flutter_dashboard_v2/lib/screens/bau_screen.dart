import 'package:flutter/material.dart';

import '../core/presentation/telemetry_presentation.dart';
import '../core/state/gateway_controller.dart';
import '../models/gateway_models.dart';
import '../widgets/common_widgets.dart';

class BauScreen extends StatelessWidget {
  const BauScreen({super.key, required this.controller});

  final GatewayController controller;

  @override
  Widget build(BuildContext context) {
    final bank = controller.plant.bank;
    if (bank == null) return const Center(child: Text('No BAU/bank snapshot received yet.'));

    final bankVoltage = _effectiveBankVoltage(bank, controller.plant.racks);
    final bankCurrent = _effectiveBankCurrent(bank, controller.plant.racks);

    return RefreshIndicator(
      onRefresh: controller.refreshCompact,
      child: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          SectionHeader(
            'BMS Bank / BAU',
            subtitle: '${bank.telemetry.length} mapped points • ${bank.online ? 'Online' : 'Offline'} • ${bank.timestamp == null ? 'No timestamp' : shortTime(bank.timestamp!)}',
            trailing: StatusPill(label: bank.online ? 'Online' : 'Offline', good: bank.online),
          ),
          const SizedBox(height: 16),
          MetricGrid(
            children: [
              MetricTile(
                label: 'Bank voltage',
                value: bankVoltage.text,
                subtitle: bankVoltage.note,
                icon: Icons.bolt,
                emphasis: true,
              ),
              MetricTile(
                label: 'Bank current',
                value: bankCurrent.text,
                subtitle: bankCurrent.note,
                icon: Icons.electric_meter,
                emphasis: true,
              ),
              _metric(bank, 'soc', 'State of charge', Icons.battery_5_bar, emphasis: true),
              _metric(bank, 'bank_soh', 'State of health', Icons.favorite, emphasis: true),
              _metric(bank, 'echg_avl', 'Available charge energy', Icons.battery_charging_full),
              _metric(bank, 'edsg_avl', 'Available discharge energy', Icons.battery_6_bar),
              _metric(bank, 'ibank_chg_lim', 'Charge current limit', Icons.south),
              _metric(bank, 'ibank_dsg_lim', 'Discharge current limit', Icons.north),
              _metric(bank, 'bank_chgable_power', 'Charge power limit', Icons.power_input),
              _metric(bank, 'bank_dsgable_power', 'Discharge power limit', Icons.power),
              _metric(bank, 'ir', 'Insulation resistance', Icons.shield_outlined),
              _metric(bank, 'grid_connect_clu_num', 'Connected racks', Icons.hub),
            ],
          ),
          const SizedBox(height: 24),
          TelemetrySection(
            title: 'Electrical and operating limits',
            asset: bank,
            entries: entriesForKeys(bank, const [
              'bank_voltage', 'ibank', 'ir', 'ibank_chg_lim', 'ibank_dsg_lim',
              'bank_chgable_power', 'bank_dsgable_power', 'vrack_diff', 'irack_diff',
            ]),
          ),
          TelemetrySection(
            title: 'Battery capacity and health',
            asset: bank,
            entries: entriesForKeys(bank, const [
              'soc', 'bank_soh', 'echg_avl', 'edsg_avl', 'grid_connect_clu_num',
              'system_total_racks', 'min_connected_racks',
            ]),
          ),
          TelemetrySection(
            title: 'Cell-voltage summary',
            asset: bank,
            entries: entriesForKeys(bank, const [
              'vcell_max', 'vcell_max_rack', 'vcell_max_pack', 'vcell_max_position',
              'vcell_min', 'vcell_min_rack', 'vcell_min_pack', 'vcell_min_position', 'vavg',
            ]),
          ),
          TelemetrySection(
            title: 'Thermal summary',
            asset: bank,
            entries: entriesForKeys(bank, const [
              'tcell_max', 'tcell_max_rack', 'tcell_max_pack', 'tcell_max_position',
              'tcell_min', 'tcell_min_rack', 'tcell_min_pack', 'tcell_min_position', 'tavg',
            ]),
          ),
          TelemetrySection(
            title: 'Energy counters',
            asset: bank,
            entries: entriesWhere(bank, (key, point) {
              final lower = key.toLowerCase();
              return lower.contains('energy') || lower.contains('echg') || lower.contains('edsg');
            }),
            initiallyExpanded: false,
          ),
          TelemetrySection(
            title: 'Operating states and communication',
            asset: bank,
            entries: entriesWhere(bank, (key, point) {
              if ((point.category ?? '').toLowerCase() != 'signal') return false;
              final lower = '${key}_${point.nameEn ?? ''}'.toLowerCase();
              return !lower.contains('alarm') && !lower.contains('fault') && !lower.contains('warn');
            }),
            initiallyExpanded: false,
          ),
          TelemetrySection(
            title: 'Alarms and faults',
            asset: bank,
            entries: entriesWhere(bank, (key, point) {
              final lower = '${key}_${point.nameEn ?? ''}'.toLowerCase();
              return lower.contains('alarm') || lower.contains('fault') || lower.contains('warn');
            }),
          ),
          TelemetrySection(
            title: 'Configuration and thresholds',
            subtitle: 'Read-only commissioning view; writes remain disabled.',
            asset: bank,
            entries: entriesWhere(bank, (key, point) =>
                (point.category ?? '').toLowerCase() == 'parameter' ||
                (point.category ?? '').toLowerCase() == 'control'),
            initiallyExpanded: false,
          ),
          const SizedBox(height: 16),
          Card(
            clipBehavior: Clip.antiAlias,
            child: ExpansionTile(
              title: const Text('All BAU points', style: TextStyle(fontWeight: FontWeight.w800)),
              subtitle: const Text('Search every raw and decoded point'),
              childrenPadding: const EdgeInsets.fromLTRB(12, 8, 12, 16),
              children: [EngineeringTable(asset: bank, maxHeight: 620)],
            ),
          ),
          const SizedBox(height: 40),
        ],
      ),
    );
  }

  Widget _metric(
    AssetSnapshot bank,
    String key,
    String label,
    IconData icon, {
    bool emphasis = false,
  }) {
    final point = bank.telemetry[key];
    final shown = point == null
        ? const PresentedValue(value: '--', unit: '', valid: false)
        : presentPoint(bank.assetType, key, point);
    return MetricTile(
      label: label,
      value: shown.text,
      subtitle: shown.note,
      icon: icon,
      emphasis: emphasis,
    );
  }

  PresentedValue _effectiveBankVoltage(AssetSnapshot bank, List<AssetSnapshot> racks) {
    final point = bank.telemetry['bank_voltage'];
    if (point?.value is num && (point!.value as num) > 0) {
      return presentPoint(bank.assetType, 'bank_voltage', point);
    }
    final values = racks
        .map((rack) => rack.telemetry['vrack']?.value)
        .whereType<num>()
        .where((value) => value > 0)
        .map((value) => value.toDouble())
        .toList();
    if (values.isEmpty) return const PresentedValue(value: '--', unit: 'V', valid: false);
    final average = values.reduce((a, b) => a + b) / values.length;
    return PresentedValue(
      value: average.toStringAsFixed(1),
      unit: 'V',
      note: 'Derived from ${values.length} rack voltages; BAU bank-voltage register reports 0 V',
    );
  }

  PresentedValue _effectiveBankCurrent(AssetSnapshot bank, List<AssetSnapshot> racks) {
    final point = bank.telemetry['ibank'];
    if (point?.value is num && (point!.value as num).abs() > 0) {
      return presentPoint(bank.assetType, 'ibank', point);
    }
    final values = racks
        .map((rack) => rack.telemetry['irack']?.value)
        .whereType<num>()
        .map((value) => value.toDouble())
        .toList();
    if (values.isEmpty) return const PresentedValue(value: '--', unit: 'A', valid: false);
    final sum = values.fold<double>(0, (total, value) => total + value);
    return PresentedValue(
      value: sum.toStringAsFixed(1),
      unit: 'A',
      note: 'Sum of rack currents; BAU bank-current register reports 0 A',
    );
  }
}
