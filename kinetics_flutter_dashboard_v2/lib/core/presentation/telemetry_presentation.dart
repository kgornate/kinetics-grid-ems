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
  // PCS measurements and status registers from the three-phase three-wire protocol.
  'dc_bus_voltage': 'DC bus voltage',
  'dc_bus_current': 'DC bus current',
  'battery_voltage': 'Battery voltage',
  'battery_current': 'Battery current',
  'dc_power': 'DC power',
  'grid_ab_voltage': 'Grid AB line voltage',
  'grid_bc_voltage': 'Grid BC line voltage',
  'grid_ca_voltage': 'Grid CA line voltage',
  'grid_a_current': 'Grid phase A current',
  'grid_b_current': 'Grid phase B current',
  'grid_c_current': 'Grid phase C current',
  'grid_n_current': 'Grid neutral current',
  'power_factor': 'Power factor',
  'grid_frequency': 'Grid frequency',
  'grid_active_power': 'Grid active power',
  'grid_reactive_power': 'Grid reactive power',
  'grid_apparent_power': 'Grid apparent power',
  'igbt_a_temperature': 'IGBT A temperature',
  'igbt_b_temperature': 'IGBT B temperature',
  'igbt_c_temperature': 'IGBT C temperature',
  'cabinet_temperature': 'Cabinet temperature',
  'positive_bus_voltage': 'Positive DC bus voltage',
  'negative_bus_voltage': 'Negative DC bus voltage',
  'inverter_ab_voltage': 'Inverter AB line voltage',
  'inverter_bc_voltage': 'Inverter BC line voltage',
  'inverter_ca_voltage': 'Inverter CA line voltage',
  'pcc_ab_voltage': 'PCC AB line voltage',
  'reg_112c': 'PCC BC line voltage',
  'reg_112d': 'PCC CA line voltage',
  'auxiliary_bus_voltage': 'Auxiliary bus voltage',
  'phase_a_to_ground_voltage': 'Phase A-to-ground voltage',
  'phase_b_to_ground_voltage': 'Phase B-to-ground voltage',
  'phase_c_to_ground_voltage': 'Phase C-to-ground voltage',
  'battery_positive_ground_impedance': 'Battery positive-to-ground impedance',
  'battery_negative_ground_impedance': 'Battery negative-to-ground impedance',
  'operating_state': 'Operating state',
  'status_word_1': 'Control and authorization status',
  'status_word_2': 'Grid and battery status',
  'status_word_3': 'Safety and operating status',
  'actual_product_mode': 'Product operating mode',
  'actual_pq_mode': 'PQ operating mode',
  'reg_1210': 'PCS input/status word',
  'reg_1211': 'System fault word 1',
  'reg_1212': 'System fault word 2',
  'reg_1213': 'Voltage and frequency fault word',
  'reg_1214': 'Thermal fault word',
  'reg_1215': 'Hardware overcurrent fault word',
  'reg_1216': 'Hardware interlock fault word',
  'reg_1217': 'PWM and inverter enable word',
  'reg_1218': 'Converter protection fault word',
  'reg_1219': 'Derating and permission status word',
  'reg_121a': 'Scheduling and BMS communication status word',
  'reg_1400': 'Remote start/stop command state',
  'reg_1401': 'HMI start/stop command state',
  'reg_1402': 'Remote/local mode setting',
  'reg_1403': 'Rated power setting',
  'reg_1404': 'Rated grid voltage setting',
  'reg_1405': 'Rated grid frequency setting',
  'reg_1406': 'Product operating mode setting',
  'reg_1407': 'PQ operating mode setting',
  'reg_1408': 'VSG feature settings',
  'reg_1409': 'Active power setpoint',
  'reg_140a': 'Reactive power setpoint',
  'reg_140b': 'Power-factor setpoint',
  'reg_140c': 'DC voltage setpoint',
  'reg_140d': 'DC current setpoint',
  'reg_140e': 'AC voltage setpoint',
  'reg_140f': 'AC current setpoint',
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
      .replaceAll('kVar', 'kvar')
      .replaceAll('KVA', 'kVA')
      .replaceAll('Kva', 'kVA');
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


  if (assetType == 'pcs' && value is num) {
    if (key == 'operating_state') {
      return PresentedValue(
        value: pcsOperatingStateLabel(value.toInt()),
        unit: '',
        note: 'Raw 0x${value.toInt().toRadixString(16).toUpperCase().padLeft(4, '0')}',
      );
    }
    if (key == 'actual_product_mode') {
      return PresentedValue(
        value: pcsProductModeLabel(value.toInt()),
        unit: '',
        note: 'Mode ${value.toInt()}',
      );
    }
    if (key == 'actual_pq_mode') {
      return PresentedValue(
        value: pcsPqModeLabel(value.toInt()),
        unit: '',
        note: 'Mode ${value.toInt()}',
      );
    }
    if (key == 'status_word_1' ||
        key == 'status_word_2' ||
        key == 'status_word_3') {
      return PresentedValue(
        value: '0x${value.toInt().toRadixString(16).toUpperCase().padLeft(4, '0')}',
        unit: '',
        note: 'Decoded on the Operating status page',
      );
    }
    if (key == 'reg_1400' || key == 'reg_1401') {
      final raw = value.toInt() & 0xFFFF;
      final label = raw == 0xFF00
          ? 'Start command'
          : raw == 0x00FF
              ? 'Stop command'
              : 'Command 0x${raw.toRadixString(16).toUpperCase().padLeft(4, '0')}';
      return PresentedValue(value: label, unit: '', note: 'Read-only command state');
    }
    if (key == 'reg_1402') {
      final raw = value.toInt() & 0xFFFF;
      final label = raw == 0xFF00
          ? 'Local mode'
          : raw == 0x00FF
              ? 'Remote mode'
              : 'Mode 0x${raw.toRadixString(16).toUpperCase().padLeft(4, '0')}';
      return PresentedValue(value: label, unit: '', note: 'Read-only setting');
    }
    if (key == 'reg_1403') {
      return PresentedValue(
        value: _formatNumber(value, decimals: 0),
        unit: 'kW',
        note: 'Rated power setting',
      );
    }
    if (key == 'reg_1404') {
      return PresentedValue(
        value: _formatNumber(value, decimals: 0),
        unit: 'V',
        note: 'Rated grid voltage',
      );
    }
    if (key == 'reg_1406') {
      return PresentedValue(
        value: pcsProductModeLabel(value.toInt()),
        unit: '',
        note: 'Configured product mode',
      );
    }
    if (key == 'reg_1407') {
      return PresentedValue(
        value: pcsPqModeLabel(value.toInt()),
        unit: '',
        note: 'Configured PQ mode',
      );
    }
    if (key == 'reg_1408') {
      final raw = value.toInt();
      final enabled = <String>[
        if ((raw & (1 << 1)) != 0) 'Primary voltage control',
        if ((raw & (1 << 2)) != 0) 'Primary frequency control',
        if ((raw & (1 << 3)) != 0) 'Grid reactive dispatch',
        if ((raw & (1 << 4)) != 0) 'Grid active dispatch',
      ];
      return PresentedValue(
        value: enabled.isEmpty ? 'All VSG features off' : enabled.join(', '),
        unit: '',
        note: 'Raw 0x${raw.toRadixString(16).toUpperCase().padLeft(4, '0')}',
      );
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
  if (category == 'status') return 'Operating status and fault words';
  if (category == 'version') return 'Software and protocol versions';
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


String pcsOperatingStateLabel(int raw) {
  const labels = <int, String>{
    0: 'Stop',
    1: 'Soft start',
    2: 'Self-check',
    3: 'Standby',
    4: 'Running',
    5: 'Energy-saving run',
    6: 'Scheduled run',
    7: 'Derated run',
    8: 'Off-grid run',
    9: 'Grid-connected run',
    10: 'Fault shutdown',
  };
  final active = <String>[];
  for (final entry in labels.entries) {
    if ((raw & (1 << entry.key)) != 0) active.add(entry.value);
  }
  return active.isEmpty ? 'Unknown' : active.join(' + ');
}

String pcsProductModeLabel(int value) {
  const labels = <int, String>{
    0: 'Standalone inverter',
    1: 'PQ mode',
    2: 'Aging/test run',
    3: 'VSG mode',
    4: 'AC voltage-source mode',
    5: 'Test mode',
  };
  return labels[value] ?? 'Mode $value';
}

String pcsPqModeLabel(int value) {
  const labels = <int, String>{
    0: 'Constant power',
    1: 'Constant DC voltage',
    2: 'Constant DC current',
    3: 'Constant grid voltage',
    4: 'Constant AC current',
    5: 'Smart mode',
    6: 'Scheduled dispatch',
    7: 'Island mode',
    8: 'Frequency regulation',
    9: 'Low-voltage ride-through',
    10: 'High-voltage ride-through',
  };
  return labels[value] ?? 'Mode $value';
}

String pcsControlLocation(AssetSnapshot asset) {
  final raw = asset.telemetry['status_word_1']?.value;
  if (raw is! num) return '--';
  return (raw.toInt() & 0x0001) != 0 ? 'Remote' : 'Local';
}

String pcsAuthorizationState(AssetSnapshot asset) {
  final raw = asset.telemetry['status_word_1']?.value;
  if (raw is! num) return '--';
  return (raw.toInt() & 0x0002) != 0 ? 'Authorized' : 'Not authorized';
}

String pcsDcBreakerState(AssetSnapshot asset) {
  final raw = asset.telemetry['status_word_2']?.value;
  if (raw is! num) return '--';
  return (raw.toInt() & (1 << 6)) != 0 ? 'Open' : 'Closed';
}

int pcsActiveFaultBitCount(AssetSnapshot asset) {
  var count = 0;
  for (final entry in asset.telemetry.entries) {
    final key = entry.key.toLowerCase();
    if (!RegExp(r'^reg_121[0-9a]$').hasMatch(key)) continue;
    count += activeBitCount(entry.value);
  }
  return count;
}

List<String> pcsSummary(AssetSnapshot asset) {
  String shown(String key, String prefix) {
    final point = asset.telemetry[key];
    if (point == null) return '';
    return '$prefix${presentPoint('pcs', key, point).text}';
  }

  if (asset.telemetry.isEmpty) {
    return <String>[
      'Modbus RTU ID ${asset.unitId ?? '--'}',
      asset.disabled ? 'Disabled' : 'Waiting for response',
    ];
  }
  return <String>[
    pcsOperatingStateLabel((asset.telemetry['operating_state']?.value as num?)?.toInt() ?? 0),
    pcsProductModeLabel((asset.telemetry['actual_product_mode']?.value as num?)?.toInt() ?? -1),
    shown('dc_bus_voltage', 'DC '),
    shown('grid_active_power', 'P '),
    shown('grid_frequency', 'Grid '),
    shown('cabinet_temperature', 'Cabinet '),
  ];
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
