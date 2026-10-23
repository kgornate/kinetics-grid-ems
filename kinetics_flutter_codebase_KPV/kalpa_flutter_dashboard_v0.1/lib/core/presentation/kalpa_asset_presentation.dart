import '../../models/gateway_models.dart';
import 'kalpa_signal_catalog.dart';

class KalpaDetailTab {
  const KalpaDetailTab(this.id, this.title);
  final String id;
  final String title;
}

class KalpaSignalGroup {
  const KalpaSignalGroup(this.id, this.title, this.tab);
  final String id;
  final String title;
  final String tab;
}

const kalpaGroups = <KalpaSignalGroup>[
  KalpaSignalGroup('operating', 'Operating state and contactors', 'status'),
  KalpaSignalGroup('electrical', 'Electrical measurements', 'electrical'),
  KalpaSignalGroup(
    'capability',
    'Battery capacity and operating limits',
    'electrical',
  ),
  KalpaSignalGroup('energy', 'Energy counters', 'energy'),
  KalpaSignalGroup('thermal', 'Thermal measurements and extrema', 'thermal'),
  KalpaSignalGroup('cell_voltage', 'Individual cell voltages', 'cells'),
  KalpaSignalGroup('cell_temperature', 'Individual cell temperatures', 'cells'),
  KalpaSignalGroup('cell_soc', 'Individual cell SOC', 'cells'),
  KalpaSignalGroup('cell_balance', 'Cell balancing feedback', 'cells'),
  KalpaSignalGroup('pack_voltage', 'Pack voltages', 'sensors'),
  KalpaSignalGroup('pack_temperature', 'Pack terminal temperatures', 'sensors'),
  KalpaSignalGroup('dc', 'DC-side measurements', 'dc'),
  KalpaSignalGroup('ac', 'AC / grid measurements', 'ac'),
  KalpaSignalGroup('cooling', 'Cooling measurements', 'measurements'),
  KalpaSignalGroup('humidity', 'Temperature and humidity', 'measurements'),
  KalpaSignalGroup('inputs', 'Container and safety inputs', 'status'),
  KalpaSignalGroup('communication', 'Communication status', 'status'),
  KalpaSignalGroup('alarms', 'Alarm and fault registers', 'alarms'),
  KalpaSignalGroup('settings', 'Configuration and thresholds', 'settings'),
  KalpaSignalGroup('identity', 'Identity, versions and clock', 'settings'),
  KalpaSignalGroup('other', 'Other published signals', 'status'),
  KalpaSignalGroup('reserved', 'Reserved / unspecified points', 'all'),
];

String kalpaRole(String type) =>
    ['bms_bank', 'bms_rack', 'pcs'].contains(type) ? type : 'environment';

Map<String, dynamic> kalpaMetadata(String type, String key) {
  final role = kalpaSignalCatalog[kalpaRole(type)];
  var value = role is Map ? role[key] : null;
  if (value == null && kalpaRole(type) == 'environment') {
    // The backend also publishes BAMS container/safety inputs as auxiliary
    // assets. Keep their original system-level protocol metadata.
    value = (kalpaSignalCatalog['bms_bank'] as Map)[key];
  }
  return value is Map ? Map<String, dynamic>.from(value) : {};
}

List<KalpaDetailTab> kalpaTabs(String type) {
  if (type == 'bms_rack') {
    return const [
      KalpaDetailTab('overview', 'Overview'),
      KalpaDetailTab('electrical', 'Electrical'),
      KalpaDetailTab('thermal', 'Thermal'),
      KalpaDetailTab('cells', 'Cells'),
      KalpaDetailTab('sensors', 'Sensors'),
      KalpaDetailTab('alarms', 'Alarms & faults'),
      KalpaDetailTab('settings', 'Settings'),
      KalpaDetailTab('all', 'All signals'),
    ];
  }
  if (type == 'pcs') {
    return const [
      KalpaDetailTab('overview', 'Overview'),
      KalpaDetailTab('dc', 'DC side'),
      KalpaDetailTab('ac', 'AC / Grid'),
      KalpaDetailTab('thermal', 'Thermal'),
      KalpaDetailTab('status', 'Operating status'),
      KalpaDetailTab('alarms', 'Alarms & faults'),
      KalpaDetailTab('settings', 'Settings'),
      KalpaDetailTab('all', 'All signals'),
    ];
  }
  if (type == 'bms_bank') {
    return const [
      KalpaDetailTab('overview', 'Overview'),
      KalpaDetailTab('electrical', 'Electrical'),
      KalpaDetailTab('thermal', 'Thermal'),
      KalpaDetailTab('energy', 'Energy'),
      KalpaDetailTab('status', 'Operating status'),
      KalpaDetailTab('alarms', 'Alarms & faults'),
      KalpaDetailTab('settings', 'Settings'),
      KalpaDetailTab('all', 'All signals'),
    ];
  }
  return const [
    KalpaDetailTab('overview', 'Overview'),
    KalpaDetailTab('measurements', 'Measurements'),
    KalpaDetailTab('status', 'Operating status'),
    KalpaDetailTab('alarms', 'Alarms & faults'),
    KalpaDetailTab('settings', 'Settings'),
    KalpaDetailTab('all', 'All signals'),
  ];
}

String kalpaGroupFor(String type, String key, TelemetryPoint point) {
  final meta = kalpaMetadata(type, key);
  final category = (point.category ?? meta['category'] ?? '').toString();
  final k = key.toLowerCase();
  if (meta['reserved'] == true || RegExp(r'^reserv(e|ed)(_|$)').hasMatch(k)) {
    return 'reserved';
  }
  // Exact protocol categories take priority over words such as temperature,
  // current, or voltage occurring inside an alarm/setting name.
  if (['rack_alarm', 'system_alarm', 'alarm'].contains(category))
    return 'alarms';
  if ([
    'setting',
    'control_parameter',
    'control_parameter_2',
    'communication_parameter',
    'remote_control',
  ].contains(category))
    return 'settings';
  if (['identity', 'rtc'].contains(category)) return 'identity';
  if ([
    'cell_voltage',
    'cell_temperature',
    'cell_soc',
    'cell_balance',
    'pack_voltage',
    'pack_temperature',
  ].contains(category))
    return category;
  if (RegExp(r'^cell_(charge_balance|discharge_balance)_\d+$').hasMatch(k))
    return 'cell_balance';
  if (RegExp(r'^cell_voltage_\d+$').hasMatch(k)) return 'cell_voltage';
  if (RegExp(r'^cell_temperature_\d+$').hasMatch(k)) return 'cell_temperature';
  if (RegExp(r'^cell_soc_\d+$').hasMatch(k)) return 'cell_soc';
  if (k.startsWith('pack_voltage_')) return 'pack_voltage';
  if (k.startsWith('pack_') && k.contains('temperature'))
    return 'pack_temperature';
  if (k.startsWith('set_') || k.contains('setpoint')) return 'settings';
  if (k.contains('fault') ||
      k.contains('alarm') ||
      k.contains('warning') ||
      k.contains('protection') ||
      k == 'emergency_stop')
    return 'alarms';
  if (k.contains('communication') || k.contains('heartbeat'))
    return 'communication';
  if (type == 'pcs') {
    if (category == 'status' || k.contains('status') || k.contains('state'))
      return 'operating';
    if (k.contains('temperature') || k.contains('temp')) return 'thermal';
    if (k.startsWith('grid_') ||
        k.startsWith('inverter') ||
        k.startsWith('total_') ||
        k.startsWith('power_factor') ||
        k.startsWith('powerfactor') ||
        k.startsWith('activepower') ||
        k.startsWith('reactivepower') ||
        k.startsWith('apparentpower'))
      return 'ac';
    if (k.startsWith('dc_') ||
        k.contains('bus_voltage') ||
        k.contains('ground') ||
        k.contains('impedance') ||
        k.contains('bridgecurrent') ||
        k.contains('leakage'))
      return 'dc';
    return 'other';
  }
  if (['bms_rack', 'bms_bank'].contains(type)) {
    if (k.contains('energy') ||
        k.contains('charge_count') ||
        k.contains('discharge_count'))
      return 'energy';
    if (k.contains('temperature') || k.contains('_temp')) return 'thermal';
    if (k.contains('state') ||
        k.contains('feedback') ||
        k.startsWith('digital_input') ||
        k.contains('rack_count') ||
        k.contains('rack_bitmap') ||
        k.contains('protocol_version') ||
        k.endsWith('_cell_count') ||
        k.endsWith('_pack_count'))
      return 'operating';
    if (k.contains('soc') ||
        k.contains('soh') ||
        k.contains('capacity') ||
        k.contains('max_charge') ||
        k.contains('max_discharge'))
      return 'capability';
    if (k.contains('voltage') ||
        k.contains('current') ||
        k.contains('resistance'))
      return 'electrical';
    return 'other';
  }
  if (k.contains('state') ||
      k.contains('status') ||
      k.contains('control_mode') ||
      k.endsWith('_feedback'))
    return 'operating';
  if (k.startsWith('digital_input') ||
      RegExp(r'(^|_)door(_|$)').hasMatch(k) ||
      k.contains('fss_') ||
      k.contains('spray') ||
      k.contains('switch_'))
    return 'inputs';
  if (k.contains('limit') ||
      k.contains('start_temp') ||
      k.contains('stop_temp') ||
      k.contains('differential') ||
      k.contains('_cycle'))
    return 'settings';
  if (category == 'chiller' ||
      k.contains('water_') ||
      k.contains('coolant') ||
      k.contains('pump_speed'))
    return 'cooling';
  if (['dehumidifier', 'temp_humidity'].contains(category) ||
      k.contains('humidity') ||
      k.contains('indoor_temp') ||
      k.contains('ambient_temperature'))
    return 'humidity';
  return 'other';
}

String kalpaTabFor(String type, KalpaSignalGroup group) {
  if (type == 'bms_rack' && ['status', 'energy'].contains(group.tab)) {
    return group.tab == 'energy' ? 'electrical' : 'overview';
  }
  return group.tab;
}

Map<String, List<MapEntry<String, TelemetryPoint>>> kalpaGrouped(
  AssetSnapshot asset,
) {
  final result = <String, List<MapEntry<String, TelemetryPoint>>>{};
  for (final entry in asset.telemetry.entries) {
    result
        .putIfAbsent(
          kalpaGroupFor(asset.assetType, entry.key, entry.value),
          () => [],
        )
        .add(entry);
  }
  for (final entries in result.values) {
    entries.sort((a, b) => kalpaNaturalCompare(a.key, b.key));
  }
  return result;
}

int kalpaNaturalCompare(String a, String b) {
  final pattern = RegExp(r'\d+|\D+');
  final left = pattern.allMatches(a).map((m) => m[0]!).toList();
  final right = pattern.allMatches(b).map((m) => m[0]!).toList();
  for (var i = 0; i < left.length && i < right.length; i++) {
    final x = int.tryParse(left[i]), y = int.tryParse(right[i]);
    final value = x != null && y != null
        ? x.compareTo(y)
        : left[i].compareTo(right[i]);
    if (value != 0) return value;
  }
  return left.length.compareTo(right.length);
}

String kalpaPointName(String type, String key, TelemetryPoint point) =>
    point.nameEn ??
    kalpaMetadata(type, key)['name_en']?.toString() ??
    prettifyKey(key);
String kalpaPointUnit(String type, String key, TelemetryPoint point) =>
    (point.unit ?? kalpaMetadata(type, key)['unit']?.toString() ?? '')
        .replaceAll('℃', '°C');
String kalpaPointAddress(String type, String key, TelemetryPoint point) =>
    point.address ?? kalpaMetadata(type, key)['address_hex']?.toString() ?? '—';
bool kalpaPointAvailable(AssetSnapshot asset, TelemetryPoint point) =>
    asset.online &&
    ['good', 'mock'].contains(point.quality.toLowerCase()) &&
    point.value != null &&
    (point.value is! num || (point.value as num).isFinite);

String kalpaPointValue(AssetSnapshot asset, String key, TelemetryPoint point) {
  if (!kalpaPointAvailable(asset, point)) return '—';
  final meta = kalpaMetadata(asset.assetType, key);
  final value = point.value;
  final enums = meta['enum'];
  final label =
      point.enumLabel ??
      (enums is Map && value is num
          ? enums[value.toInt().toString()]?.toString()
          : null);
  return label == null ? point.displayValue : '$label (${point.displayValue})';
}
