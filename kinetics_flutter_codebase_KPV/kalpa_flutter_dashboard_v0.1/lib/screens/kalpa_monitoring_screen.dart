import 'package:flutter/material.dart';
import '../core/state/gateway_controller.dart';
import '../widgets/common_widgets.dart';
import 'kalpa_asset_detail_screen.dart';
export 'kalpa_asset_detail_screen.dart' show KalpaAssetScreen;

Map<String, dynamic> kalpaMap(dynamic value) =>
    value is Map ? Map<String, dynamic>.from(value) : <String, dynamic>{};
String kalpaNumber(dynamic value, [String unit = '', int digits = 1]) {
  if (value is! num || !value.isFinite) return '—';
  return '${value.toStringAsFixed(digits)}${unit.isEmpty ? '' : ' $unit'}';
}

String kalpaTime(dynamic value) =>
    DateTime.tryParse(
      value?.toString() ?? '',
    )?.toLocal().toString().split('.').first ??
    '—';

class KalpaMonitoringScreen extends StatelessWidget {
  const KalpaMonitoringScreen({
    super.key,
    required this.controller,
    required this.section,
  });
  final GatewayController controller;
  final String section;

  Widget _metric(String label, dynamic value, String unit, bool valid) =>
      MetricTile(label: label, value: valid ? kalpaNumber(value, unit) : '—');

  Widget _raw(BuildContext context, String assetId, String label) =>
      OutlinedButton.icon(
        onPressed: () => Navigator.of(context).push(
          MaterialPageRoute<void>(
            builder: (_) =>
                KalpaAssetScreen(controller: controller, assetId: assetId),
          ),
        ),
        icon: const Icon(Icons.dashboard_outlined),
        label: Text(label),
      );

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
    animation: controller,
    builder: (context, _) {
      final model = controller.normalized;
      final system = kalpaMap(model['battery_system']);
      final racks = kalpaMap(model['battery_racks']);
      final pcs = kalpaMap(model['pcs']);
      final pairs = kalpaMap(model['pairs']);
      final live = controller.normalizedLive;
      final systemLive = live && system['online'] == true;
      final children = <Widget>[
        SectionHeader(
          section == 'overview'
              ? 'Kalpa site overview'
              : section == 'battery'
              ? 'Lineage battery system'
              : section == 'racks'
              ? 'Battery racks'
              : section == 'pcs'
              ? 'Elecod PCS'
              : 'Auxiliary assets',
          subtitle:
              '${controller.plant.gatewayId} · ${controller.plant.mode} · Lineage BMS + Elecod PCS',
          trailing: IconButton(
            tooltip: 'Refresh cached data',
            onPressed: controller.refreshKalpa,
            icon: const Icon(Icons.refresh),
          ),
        ),
        if (!live)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: Text(
              'Normalized data unavailable or stale. ${controller.normalizedError ?? 'Waiting for a fresh snapshot.'}',
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ),
        if (controller.plant.mode == 'mock' || controller.plant.mode == 'mixed')
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 8),
            child: Text(
              'BMS/PCS mode includes simulation. The meter has its own hardware/simulation source.',
            ),
          ),
      ];
      if (section == 'overview' || section == 'battery') {
        children.add(
          MetricGrid(
            children: [
              _metric('Battery SOC', system['soc_percent'], '%', systemLive),
              _metric('Battery SOH', system['soh_percent'], '%', systemLive),
              _metric('System voltage', system['voltage_v'], 'V', systemLive),
              _metric('System current', system['current_a'], 'A', systemLive),
              _metric(
                'Charge power limit',
                system['max_charge_power_kw'],
                'kW',
                systemLive,
              ),
              _metric(
                'Discharge power limit',
                system['max_discharge_power_kw'],
                'kW',
                systemLive,
              ),
            ],
          ),
        );
        children.add(const SizedBox(height: 16));
        children.add(_raw(context, 'bms_bank', 'Open system BMS dashboard'));
      }
      if (section == 'overview') {
        final enabledPairs = pairs.values
            .map(kalpaMap)
            .where((p) => p['enabled'] != false)
            .toList();
        final totalValid =
            live &&
            enabledPairs.isNotEmpty &&
            enabledPairs.every(
              (p) =>
                  kalpaMap(p['pcs'])['online'] == true &&
                  kalpaMap(p['pcs'])['active_power_kw'] is num,
            );
        final total = enabledPairs.fold<double>(0, (sum, p) {
          final value = kalpaMap(p['pcs'])['active_power_kw'];
          return sum + (value is num ? value.toDouble() : 0);
        });
        children.add(const SizedBox(height: 20));
        children.add(
          MetricGrid(
            children: [
              _metric('Total PCS active power', total, 'kW', totalValid),
              MetricTile(
                label: 'Pairs online',
                value: live
                    ? '${enabledPairs.where((p) => p['online'] == true).length}/${enabledPairs.length}'
                    : '—',
              ),
              MetricTile(
                label: 'Active alarms',
                value: '${controller.activeAlarms.length}',
              ),
              MetricTile(
                label: 'Meter',
                value: controller.meterError != null
                    ? 'API unavailable'
                    : controller.meter?['status']?.toString() ?? 'Not enabled',
              ),
            ],
          ),
        );
        children.add(
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 20),
            child: Text(
              'Four battery / PCS pairs',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
            ),
          ),
        );
        for (final pair in enabledPairs) {
          final battery = kalpaMap(pair['battery']),
              converter = kalpaMap(pair['pcs']);
          children.add(
            _assetCard(
              context,
              pair['pair_id']?.toString() ?? 'Pair',
              live && pair['online'] == true,
              [
                'SOC: ${live && battery['online'] == true ? kalpaNumber(battery['soc_percent'], '%') : '—'}',
                'Rack voltage: ${live && battery['online'] == true ? kalpaNumber(battery['voltage_v'], 'V') : '—'}',
                'PCS active power: ${live && converter['online'] == true ? kalpaNumber(converter['active_power_kw'], 'kW') : '—'}',
                'PCS: ${converter['asset_id'] ?? pair['pcs_asset_id'] ?? '—'}',
              ],
            ),
          );
        }
      }
      if (section == 'battery') {
        children.add(
          MetricGrid(
            children: [
              _metric(
                'Charge current limit',
                system['max_charge_current_a'],
                'A',
                systemLive,
              ),
              _metric(
                'Discharge current limit',
                system['max_discharge_current_a'],
                'A',
                systemLive,
              ),
              _metric(
                'Maximum cell voltage',
                system['max_cell_voltage_v'],
                'V',
                systemLive,
              ),
              _metric(
                'Minimum cell voltage',
                system['min_cell_voltage_v'],
                'V',
                systemLive,
              ),
              _metric(
                'Maximum cell temperature',
                system['max_cell_temperature_c'],
                '°C',
                systemLive,
              ),
              _metric(
                'Minimum cell temperature',
                system['min_cell_temperature_c'],
                '°C',
                systemLive,
              ),
            ],
          ),
        );
        children.add(
          Padding(
            padding: const EdgeInsets.all(12),
            child: Text(
              'State: ${systemLive ? system['state'] ?? 'Unknown' : 'Unavailable'} · Measured: ${kalpaTime(system['timestamp'])}',
            ),
          ),
        );
      }
      if (section == 'racks' || section == 'pcs') {
        final items = (section == 'racks' ? racks : pcs).entries.toList()
          ..sort((a, b) => a.key.compareTo(b.key));
        if (items.isEmpty) children.add(const Text('No assets received yet.'));
        for (final entry in items) {
          final asset = kalpaMap(entry.value),
              valid = live && asset['online'] == true;
          final rows = section == 'racks'
              ? <String>[
                  'SOC: ${valid ? kalpaNumber(asset['soc_percent'], '%') : '—'}',
                  'SOH: ${valid ? kalpaNumber(asset['soh_percent'], '%') : '—'}',
                  'Voltage: ${valid ? kalpaNumber(asset['voltage_v'], 'V') : '—'}',
                  'Current: ${valid ? kalpaNumber(asset['current_a'], 'A') : '—'}',
                  'Charge limit: ${valid ? kalpaNumber(asset['max_charge_power_kw'], 'kW') : '—'}',
                  'Discharge limit: ${valid ? kalpaNumber(asset['max_discharge_power_kw'], 'kW') : '—'}',
                  'State: ${valid ? asset['state'] ?? 'Unknown' : 'Unavailable'}',
                ]
              : <String>[
                  'Active power: ${valid ? kalpaNumber(asset['active_power_kw'], 'kW') : '—'}',
                  'Reactive power: ${valid ? kalpaNumber(asset['reactive_power_kvar'], 'kvar') : '—'}',
                  'DC voltage: ${valid ? kalpaNumber(asset['dc_voltage_v'], 'V') : '—'}',
                  'DC current: ${valid ? kalpaNumber(asset['dc_current_a'], 'A') : '—'}',
                  'Grid frequency: ${valid ? kalpaNumber(asset['grid_frequency_hz'], 'Hz', 2) : '—'}',
                  'Running: ${valid ? asset['running'] ?? 'Unknown' : 'Unavailable'}',
                  'Fault: ${valid ? asset['faulted'] ?? 'Unknown' : 'Unavailable'}',
                ];
          children.add(
            _assetCard(
              context,
              section == 'racks'
                  ? 'Rack ${entry.key}'
                  : entry.key.toUpperCase(),
              valid,
              rows,
              action: _raw(
                context,
                asset['asset_id']?.toString() ?? entry.key,
                section == 'racks'
                    ? 'Open rack dashboard'
                    : 'Open PCS dashboard',
              ),
            ),
          );
        }
      }
      if (section == 'environment') {
        for (final asset in controller.plant.environment) {
          children.add(
            _assetCard(context, asset.label ?? asset.assetId, asset.online, [
              '${asset.telemetry.length} signals',
              'Last sample: ${kalpaTime(asset.timestamp)}',
            ], action: _raw(context, asset.assetId, 'Open asset dashboard')),
          );
        }
        if (controller.plant.environment.isEmpty)
          children.add(
            const Text(
              'No auxiliary assets published. Check commissioning configuration.',
            ),
          );
      }
      return RefreshIndicator(
        onRefresh: controller.refreshKalpa,
        child: ListView(padding: const EdgeInsets.all(20), children: children),
      );
    },
  );

  Widget _assetCard(
    BuildContext context,
    String title,
    bool online,
    List<String> rows, {
    Widget? action,
  }) => Card(
    child: Padding(
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  title,
                  style: Theme.of(context).textTheme.titleLarge,
                ),
              ),
              StatusPill(
                label: online ? 'Online' : 'Offline / stale',
                good: online,
              ),
            ],
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 24,
            runSpacing: 10,
            children: rows.map((row) => Text(row)).toList(),
          ),
          if (action != null)
            Padding(padding: const EdgeInsets.only(top: 12), child: action),
        ],
      ),
    ),
  );
}
