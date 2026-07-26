import 'dart:typed_data';

import '../../models/gateway_models.dart';

class PresentedValue {
  const PresentedValue({
    required this.value,
    required this.unit,
    this.note,
    this.valid = true,
  });

  final String value;
  final String unit;
  final String? note;
  final bool valid;

  String get text => unit.isEmpty ? value : '$value $unit';
}

const Map<String, String> _friendlyNames = <String, String>{
  'ibank': 'Bank current',
  'bank_soh': 'Bank SOH',
  'echg_avl': 'Available charge energy',
  'edsg_avl': 'Available discharge energy',
  'ibank_chg_lim': 'Charge current limit',
  'ibank_dsg_lim': 'Discharge current limit',
  'bank_chgable_power': 'Charge power limit',
  'bank_dsgable_power': 'Discharge power limit',
  'ir': 'Insulation resistance',
  'vrack': 'Rack voltage',
  'irack': 'Rack current',
  'irack_chg_limit': 'Charge current limit',
  'irack_dsg_limit': 'Discharge current limit',
  'vcell_max': 'Maximum cell voltage',
  'vcell_min': 'Minimum cell voltage',
  'vcell_avg': 'Average cell voltage',
  'vavg': 'Average cell voltage',
  'vcell_diff': 'Cell voltage spread',
  'tcell_max': 'Maximum cell temperature',
  'tcell_min': 'Minimum cell temperature',
  'tcell_avg': 'Average cell temperature',
  'tavg': 'Average cell temperature',
  'max_bat_temp_diff': 'Cell temperature spread',
  'tterm_max': 'Maximum terminal temperature',
  'pdu_max_temp': 'Maximum PDU temperature',
  'bmu_total_vol': 'BMU accumulated voltage',
  'pre_charge_volt': 'Pre-charge voltage',
  'pre_charge_state': 'Pre-charge state',
  'bcu_run_state': 'Rack operating state',
  'current_state': 'Charge/discharge state',
  'contactor_state': 'Contactor state',
  'rack_inner_soc': 'Internal rack SOC',
  'grid_connect_clu_num': 'Connected racks',
  'system_total_racks': 'Configured racks',
  'run_state': 'Bank operating state',
  'chg_dsg_state': 'Bank charge/discharge state',
  'bank_echg_cum': 'Lifetime charged energy',
  'bank_edsg_cum': 'Lifetime discharged energy',
  'bank_today_chg_energy': 'Charged energy today',
  'bank_today_dsg_energy': 'Discharged energy today',
  'month_echg_cum': 'Charged energy this month',
  'month_edsg_cum': 'Discharged energy this month',
  'year_echg_cum': 'Charged energy this year',
  'year_edsg_cum': 'Discharged energy this year',
  'aircond_1_1': 'Unit status',
  'aircond_1_2': 'Indoor fan',
  'aircond_1_3': 'Outdoor fan',
  'aircond_1_4': 'Compressor',
  'aircond_1_5': 'Electric heater',
  'aircond_1_7': 'Coil temperature',
  'aircond_1_9': 'Condensing temperature',
  'aircond_1_10': 'Indoor temperature',
  'aircond_1_11': 'Humidity',
  'aircond_1_14': 'AC input voltage',
  'liquidcool_1_1': 'Pump speed',
  'liquidcool_1_2': 'Compressor 1',
  'liquidcool_1_3': 'Compressor 2',
  'liquidcool_1_4': 'Electric heater',
  'liquidcool_1_5': 'Condenser fan',
  'liquidcool_1_6': 'Outlet coolant temperature',
  'liquidcool_1_7': 'Return coolant temperature',
  'liquidcool_1_8': 'Outlet pressure',
  'liquidcool_1_9': 'Return pressure',
  'liquidcool_1_10': 'Ambient temperature',
  'liquidcool_1_12': 'Unit status',
  'liquidcool_1_19': 'Alarm level',
  'dehumidifier_1': 'Operating status',
  'dehumidifier_2': 'Alarm status',
  'dehumidifier_3': 'Dew-point temperature',
  'dehumidifier_4': 'Humidity',
  'dehumidifier_5': 'Temperature channel 1 (raw)',
  'dehumidifier_6': 'Temperature channel 2 (raw)',
  'dehumidifier2_1': 'Operating status',
  'dehumidifier2_2': 'Alarm status',
  'dehumidifier2_3': 'Dew-point temperature',
  'dehumidifier2_4': 'Humidity',
  'dehumidifier2_5': 'Temperature channel 1 (raw)',
  'dehumidifier2_6': 'Temperature channel 2 (raw)',
  'essmeter_1_1': 'Phase A voltage',
  'essmeter_1_2': 'Phase B voltage',
  'essmeter_1_3': 'Phase C voltage',
  'essmeter_1_4': 'Line voltage AB',
  'essmeter_1_5': 'Line voltage BC',
  'essmeter_1_6': 'Line voltage CA',
  'essmeter_1_7': 'Phase A current',
  'essmeter_1_8': 'Phase B current',
  'essmeter_1_9': 'Phase C current',
  'essmeter_1_10': 'Neutral current',
  'essmeter_1_11': 'Phase A active power',
  'essmeter_1_12': 'Phase B active power',
  'essmeter_1_13': 'Phase C active power',
  'essmeter_1_14': 'Total active power',
  'essmeter_1_15': 'Phase A reactive power',
  'essmeter_1_16': 'Phase B reactive power',
  'essmeter_1_17': 'Phase C reactive power',
  'essmeter_1_18': 'Total reactive power',
  'essmeter_1_19': 'Phase A apparent power',
  'essmeter_1_20': 'Phase B apparent power',
  'essmeter_1_21': 'Phase C apparent power',
  'essmeter_1_22': 'Total apparent power',
  'essmeter_1_23': 'Phase A power factor',
  'essmeter_1_24': 'Phase B power factor',
  'essmeter_1_25': 'Phase C power factor',
  'essmeter_1_26': 'Total power factor',
  'essmeter_1_27': 'Frequency',
  'essmeter_1_28': 'Average phase voltage',
  'essmeter_1_29': 'Average line voltage',
  'essmeter_1_30': 'Average current',
  'di1h': 'Emergency stop',
  'di2h': 'Remote/local feedback',
  'di4h': 'Fire alarm level 2',
  'di5h': 'Fire-system fault',
  'di6h': 'Fire alarm level 1',
  'di7l': 'Access-door feedback',
  'di8l': 'Electrical-cabinet water leak',
  'di10l': 'Battery-cabinet water leak',
  'di11l': 'DC circuit breaker open',
  'di12l': 'AC surge/lightning fault',
  'di13h': 'Fire-suppression feedback',
  'di14l': 'UPS power-off feedback',
  'do1': 'PCS dry contact',
  'do2': 'Fault indicator',
  'do3': 'Run indicator',
  'do4': 'AC/DC trip relay',
};

String friendlyName(String key, TelemetryPoint point) {
  final mapped = _friendlyNames[key];
  if (mapped != null) return mapped;
  final sourceName = point.nameEn?.trim();
  if (sourceName != null && sourceName.isNotEmpty) {
    return sourceName
        .replaceAll(RegExp(r'[_]+'), ' ')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
  }
  return prettifyKey(key);
}

String normaliseUnit(String? unit) {
  if (unit == null) return '';
  final cleaned = unit.trim();
  if (cleaned.isEmpty) return '';
  return cleaned
      .replaceAll('â', '°C')
      .replaceAll('℃', '°C')
      .replaceAll('â°', '‰')
      .replaceAll('kÎ©', 'kΩ')
      .replaceAll('mÎ©', 'mΩ')
      .replaceAll('Î©/V', 'Ω/V')
      .replaceAll('Î©', 'Ω')
      .replaceAll('Kvar', 'kvar')
      .replaceAll('KVA', 'kVA');
}

PresentedValue presentPoint(
  String assetType,
  String key,
  TelemetryPoint point,
) {
  dynamic value = point.value;
  var unit = normaliseUnit(point.unit);
  String? note;

  if (assetType == 'energy_meter' && key.startsWith('essmeter_1_')) {
    final raw = point.raw ?? point.value;
    if (raw is num) {
      value = float32FromUint32(raw.toInt());
      note = 'Decoded as IEEE-754 float from the current U32 payload';
    }
  }

  final isPerMille = unit == '‰' ||
      ((key == 'soc' || key == 'soh' || key == 'rack_inner_soc') &&
          value is num &&
          value > 100);
  if (isPerMille && value is num) {
    value = value / 10.0;
    unit = '%';
    note ??= 'Converted from per-mille';
  }

  if (value == null) {
    return PresentedValue(value: '--', unit: unit, note: note, valid: false);
  }
  if (value is List) {
    final populated = value.where((item) => item is num ? item != 0 : item != null).length;
    return PresentedValue(
      value: '$populated/${value.length}',
      unit: 'channels',
      note: note,
    );
  }
  if (value is Map) {
    return PresentedValue(value: '${value.length}', unit: 'fields', note: note);
  }

  if (_isBinaryState(key, point) && value is num) {
    final active = value != 0;
    return PresentedValue(
      value: _binaryLabel(key, active),
      unit: '',
      note: 'Raw ${_formatNumber(value, decimals: 0)}',
    );
  }

  if (unit == 'Hex' && value is num) {
    return PresentedValue(
      value: '0x${value.toInt().toRadixString(16).toUpperCase().padLeft(4, '0')}',
      unit: '',
      note: note,
    );
  }

  if (value is num) {
    final decimals = _decimalsFor(unit, value);
    return PresentedValue(
      value: _formatNumber(value, decimals: decimals),
      unit: unit,
      note: note,
      valid: value.isFinite,
    );
  }

  return PresentedValue(value: value.toString(), unit: unit, note: note);
}

bool _isBinaryState(String key, TelemetryPoint point) {
  if (point.value is! num) return false;
  final lower = '${key}_${point.nameEn ?? ''}'.toLowerCase();
  if (lower.contains('alarm') || lower.contains('fault')) return true;
  if (key.startsWith('di') || key.startsWith('do')) return true;
  if (lower.contains('status') || lower.contains('state')) {
    return point.value == 0 || point.value == 1;
  }
  return false;
}

String _binaryLabel(String key, bool active) {
  final lower = key.toLowerCase();
  if (lower.contains('alarm') ||
      lower.contains('fault') ||
      lower.contains('leak') ||
      lower.contains('e_stop') ||
      lower.contains('estop')) {
    return active ? 'Active' : 'Normal';
  }
  if (lower.startsWith('di') || lower.startsWith('do')) {
    return active ? 'Active' : 'Inactive';
  }
  return active ? 'On' : 'Off';
}

int _decimalsFor(String unit, num value) {
  if (unit == 'mV' || unit == 'mΩ' || unit == 'kWh' || unit == 'Ah') return 0;
  if (unit == '%' || unit == '°C' || unit == 'V' || unit == 'A' || unit == 'kW' || unit == 'kvar' || unit == 'kVA' || unit == 'Hz' || unit == 'Bar') {
    return value.abs() < 1000 ? 1 : 0;
  }
  return value is int ? 0 : 2;
}

String _formatNumber(num value, {required int decimals}) {
  if (!value.isFinite) return '--';
  var text = value.toStringAsFixed(decimals);
  if (decimals > 0) {
    text = text.replaceFirst(RegExp(r'\.?0+$'), '');
  }
  return text;
}

double float32FromUint32(int bits) {
  final data = ByteData(4)..setUint32(0, bits & 0xFFFFFFFF, Endian.big);
  return data.getFloat32(0, Endian.big).toDouble();
}

String categoryTitle(String key, TelemetryPoint point) {
  final category = (point.category ?? '').toLowerCase();
  if (category == 'control') return 'Control and command registers';
  if (category == 'parameter') return 'Configuration and thresholds';
  if (category == 'signal') {
    final lower = '${key}_${point.nameEn ?? ''}'.toLowerCase();
    if (lower.contains('alarm') || lower.contains('fault') || lower.contains('warn')) {
      return 'Alarms and faults';
    }
    return 'Operating states and signals';
  }

  final lower = '${key}_${point.nameEn ?? ''}'.toLowerCase();
  if (lower.contains('temp')) return 'Thermal measurements';
  if (lower.contains('energy') || lower.contains('echg') || lower.contains('edsg')) {
    return 'Energy counters';
  }
  if (lower.contains('soc') || lower.contains('soh') || lower.contains('cell')) {
    return 'Battery health and cells';
  }
  return 'Electrical measurements';
}

List<MapEntry<String, TelemetryPoint>> entriesForKeys(
  AssetSnapshot asset,
  Iterable<String> keys,
) {
  final result = <MapEntry<String, TelemetryPoint>>[];
  for (final key in keys) {
    final point = asset.telemetry[key];
    if (point != null) result.add(MapEntry(key, point));
  }
  return result;
}

List<MapEntry<String, TelemetryPoint>> entriesWhere(
  AssetSnapshot asset,
  bool Function(String key, TelemetryPoint point) test,
) {
  return asset.telemetry.entries.where((entry) => test(entry.key, entry.value)).toList();
}

int activeBitCount(TelemetryPoint? point) {
  if (point == null) return 0;
  return point.bitfields.values.where((value) => value == 1 || value == true).length;
}

List<MapEntry<String, dynamic>> activeBits(TelemetryPoint point) {
  return point.bitfields.entries
      .where((entry) => entry.value == 1 || entry.value == true)
      .toList();
}

List<String> environmentSummary(AssetSnapshot asset) {
  String shown(String key, {String prefix = ''}) {
    final point = asset.telemetry[key];
    if (point == null) return '';
    return '$prefix${presentPoint(asset.assetType, key, point).text}';
  }

  switch (asset.assetType) {
    case 'hvac':
      return [
        shown('aircond_1_10', prefix: 'Indoor '),
        shown('aircond_1_11', prefix: 'Humidity '),
        shown('aircond_1_4', prefix: 'Compressor '),
        shown('aircond_1_14', prefix: 'Supply '),
      ];
    case 'liquid_cooling':
      return [
        shown('liquidcool_1_6', prefix: 'Outlet '),
        shown('liquidcool_1_7', prefix: 'Return '),
        shown('liquidcool_1_1', prefix: 'Pump '),
        shown('liquidcool_1_8', prefix: 'Pressure '),
      ];
    case 'energy_meter':
      return [
        shown('essmeter_1_29', prefix: 'Voltage '),
        shown('essmeter_1_30', prefix: 'Current '),
        shown('essmeter_1_14', prefix: 'Active power '),
        shown('essmeter_1_27', prefix: 'Frequency '),
      ];
    case 'dehumidifier_1':
      return [
        shown('dehumidifier_4', prefix: 'Humidity '),
        shown('dehumidifier_3', prefix: 'Dew point '),
        shown('dehumidifier_2', prefix: 'Alarm '),
      ];
    case 'dehumidifier_2':
      return [
        shown('dehumidifier2_4', prefix: 'Humidity '),
        shown('dehumidifier2_3', prefix: 'Dew point '),
        shown('dehumidifier2_2', prefix: 'Alarm '),
      ];
    case 'safety_io':
      return [
        shown('di1h', prefix: 'E-stop '),
        shown('di6h', prefix: 'Fire L1 '),
        shown('di4h', prefix: 'Fire L2 '),
        shown('di8l', prefix: 'Water leak '),
      ];
    default:
      return ['${asset.telemetry.length} telemetry points'];
  }
}
