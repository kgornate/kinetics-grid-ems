// Standalone Dart checks: no Flutter tool, gateway or external network.
import 'dart:convert';
import 'dart:io';
import '../lib/models/gateway_models.dart';
import '../lib/core/presentation/kalpa_asset_presentation.dart';
import '../lib/core/presentation/kalpa_signal_catalog.dart';

int checks = 0;
void check(bool value, String message) {
  if (!value) throw StateError(message);
  checks++;
  stdout.writeln('PASS: $message');
}

void main() {
  for (final role in kalpaSignalCatalog.keys) {
    final type = role == 'environment' ? 'liquid_cooling' : role;
    final tabs = kalpaTabs(type).map((tab) => tab.id).toSet();
    final catalog = kalpaSignalCatalog[role] as Map;
    final everyPointReachable = catalog.keys.every((key) {
      final groupId = kalpaGroupFor(
        type,
        key.toString(),
        const TelemetryPoint(value: 0, quality: 'good'),
      );
      final group = kalpaGroups.firstWhere((group) => group.id == groupId);
      return tabs.contains(kalpaTabFor(type, group));
    });
    check(
      everyPointReachable,
      '$role: every catalog definition has a reachable category',
    );
  }
  final plant = PlantSnapshot();
  plant.applyMessage(
    jsonDecode(File('test/fixtures/compact.json').readAsStringSync())
        as Map<String, dynamic>,
  );
  for (final asset in plant.assets.values.where(
    (a) => a.assetType != 'energy_meter',
  )) {
    final grouped = kalpaGrouped(asset);
    check(
      grouped.values.fold<int>(0, (n, entries) => n + entries.length) ==
          asset.telemetry.length,
      '${asset.assetId}: every published point belongs to exactly one category',
    );
    final tabs = kalpaTabs(asset.assetType).map((tab) => tab.id).toSet();
    for (final group in kalpaGroups.where((g) => grouped.containsKey(g.id))) {
      check(
        tabs.contains(kalpaTabFor(asset.assetType, group)),
        '${asset.assetId}: ${group.title} has a reachable tab',
      );
    }
  }
  final rack = plant.assets['bms_rack_1']!;
  final groups = kalpaGrouped(rack);
  check(
    groups['cell_voltage']!.length == 416,
    'All 416 received cell voltages stay in Cells',
  );
  check(
    groups['cell_temperature']!.length == 416,
    'All 416 received cell temperatures stay in Cells',
  );
  check(
    groups['cell_soc']!.length == 416,
    'All 416 received cell SOC points stay in Cells',
  );
  check(
    groups['cell_balance']!.length == 832,
    'Both charge/discharge balance sets stay in Cells',
  );
  check(
    kalpaNaturalCompare('cell_voltage_2', 'cell_voltage_10') < 0,
    'Cell indices use numeric ordering',
  );
  check(
    kalpaMetadata('bms_rack', 'cell_voltage_1')['address'] == 201,
    'Cell register address comes from Lineage catalog',
  );
  check(
    kalpaPointUnit(
          'bms_rack',
          'cell_voltage_1',
          rack.point('cell_voltage_1')!,
        ) ==
        'V',
    'Compact cell data regains protocol unit',
  );
  check(
    kalpaPointName(
      'bms_rack',
      'rack_voltage',
      rack.point('rack_voltage')!,
    ).toLowerCase().contains('rack'),
    'Compact data regains readable parameter name',
  );
  check(
    kalpaPointValue(
      rack,
      'rack_state',
      rack.point('rack_state')!,
    ).startsWith('Normal'),
    'Lineage state is decoded using its own enum',
  );
  const alarm = TelemetryPoint(value: 1, quality: 'good');
  check(
    kalpaGroupFor('bms_rack', 'cell_voltage_upper_limit_warning', alarm) ==
        'alarms',
    'Voltage warning is an alarm, not a cell measurement',
  );
  check(
    kalpaGroupFor('pcs', 'active_power_setpoint_percent', alarm) == 'settings',
    'PCS setpoint stays in read-only Settings',
  );
  check(
    kalpaGroupFor('pcs', 'power_tube_temperature', alarm) == 'thermal',
    'PCS temperature has a Thermal table',
  );
  check(
    kalpaGroupFor('pcs', 'dc_voltage', alarm) == 'dc',
    'PCS DC voltage stays on DC side',
  );
  check(
    kalpaGroupFor('pcs', 'grid_voltage_ab', alarm) == 'ac',
    'PCS line voltage stays on AC / Grid',
  );
  check(
    kalpaGroupFor('liquid_cooling', 'set_cooling_start_temperature', alarm) ==
        'settings',
    'Cooling target stays separate from physical measurements',
  );
  check(
    kalpaGroupFor('liquid_cooling', 'outlet_water_temperature', alarm) ==
        'cooling',
    'Cooling measurement has its own category',
  );
  check(
    kalpaGroupFor('safety_io', 'indoor_temp', alarm) == 'humidity',
    'Indoor temperature is not mistaken for a door input',
  );
  check(
    kalpaGroupFor('safety_io', 'fire_start', alarm) == 'alarms',
    'BAMS safety inputs retain system alarm metadata when exposed as auxiliary assets',
  );
  check(
    kalpaGroupFor('bms_rack', 'unknown_future_signal', alarm) == 'other',
    'New unmapped signals remain visible',
  );
  check(
    kalpaGroupFor('bms_rack', 'reserve_24', alarm) == 'reserved',
    'Reserved points stay accessible in All signals',
  );
  final current = TelemetryPoint(value: -12.5, quality: 'good');
  check(
    kalpaPointValue(rack, 'rack_current', current) == '-12.5',
    'Signed Lineage current is not inverted',
  );
  check(
    kalpaPointValue(
          rack,
          'rack_current',
          const TelemetryPoint(value: 0.0, quality: 'good'),
        ) ==
        '0',
    'A valid zero is retained',
  );
  check(
    kalpaPointValue(
          rack,
          'rack_current',
          const TelemetryPoint(value: 9, quality: 'bad'),
        ) ==
        '—',
    'Bad quality value is masked',
  );
  rack.online = false;
  check(
    kalpaPointValue(rack, 'rack_current', current) == '—',
    'Offline retained value is masked',
  );
  final pcs = plant.assets['pcs_1']!;
  check(
    kalpaPointValue(
          pcs,
          'total_active_power',
          const TelemetryPoint(value: 34.5, quality: 'good'),
        ) ==
        '34.5',
    'PCS engineering value is not rescaled by old Kinetics presentation',
  );
  check(
    kalpaMetadata('pcs', 'status_word')['bitfields'] is List,
    'Elecod status flag meanings are available from the protocol',
  );
  stdout.writeln('Result: $checks category/formatting contract checks passed.');
}
