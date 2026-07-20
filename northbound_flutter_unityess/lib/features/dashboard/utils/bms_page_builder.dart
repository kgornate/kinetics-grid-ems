
import '../models/bms_source_snapshot.dart';
import '../models/pcs_fault_item.dart';
import '../models/source_summary.dart';

class BmsPageBuilder {
  const BmsPageBuilder._();

  static BmsSourceSnapshot buildForSource({
    required SourceSummary source,
    Map<String, dynamic>? bmsTelemetry,
    bool fallbackOnline = false,
  }) {
    final signals = _flattenSignals(bmsTelemetry);

    final soc = _findMeasuredValue(signals, const [
      'cluster_internal_soc',
      'display_soc',
      'soc',
      'battery_soc',
      'total_soc',
    ], allowFaultAlarm: false);

    final soh = _findMeasuredValue(signals, const [
      'soh',
      'battery_soh',
      'pack_soh',
    ], allowFaultAlarm: false);

    final packVoltageSignal = _findSignal(signals, const [
      'battery_pack_voltage',
      'pack_voltage',
      'battery_voltage',
      'total_battery_voltage',
      'cluster_total_voltage_collected',
      'pre_charge_total_voltage',
      'cell_voltage_sum_total',
      'k_total_voltage',
      'bus_voltage',
    ], allowFaultAlarm: false, preferNonZero: true);

    final packCurrentSignal = _findSignal(signals, const [
      'battery_pack_current',
      'pack_current',
      'battery_current',
      'cluster_total_current',
      'shunt_sampling_current',
      'can_hall_sampling_current',
      'current_voltage_hall_sampling_current',
      'total_current',
      'current',
    ], allowFaultAlarm: false, preferNonZero: true);

    final resistanceSignal = _findSignal(signals, const [
      'battery_cluster_internal_resistance',
      'cluster_internal_resistance',
      'internal_resistance',
      'cluster_resistance',
      'cluster_internal_resistance_value',
    ], allowFaultAlarm: false, preferNonZero: false);

    final cellVoltageSignals = _measuredCellVoltageSignals(signals);
    final maxCellVoltageDirect = _findSignal(signals, const [
      'max_voltage_value_at_shutdown',
      'max_cell_voltage',
      'max_single_cell_voltage',
      'cell_max_voltage',
      'max_voltage_value',
    ], allowFaultAlarm: false, preferNonZero: true);
    final minCellVoltageDirect = _findSignal(signals, const [
      'min_voltage_value_at_shutdown',
      'min_cell_voltage',
      'min_single_cell_voltage',
      'cell_min_voltage',
      'min_voltage_value',
    ], allowFaultAlarm: false, preferNonZero: true);
    final maxCellVoltageSignal = maxCellVoltageDirect ??
        (cellVoltageSignals.isNotEmpty
            ? _maxByNumeric(cellVoltageSignals)
            : _findSignal(signals, const [
                'max_voltage_value_at_shutdown',
                'max_voltage_value_at_alarm',
              ], allowFaultAlarm: true, preferNonZero: true));

    final minCellVoltageSignal = minCellVoltageDirect ??
        (cellVoltageSignals.isNotEmpty
            ? _minByNumeric(cellVoltageSignals)
            : _findSignal(signals, const [
                'min_voltage_value_at_shutdown',
                'min_voltage_value_at_alarm',
              ], allowFaultAlarm: true, preferNonZero: true));

    final maxCellVoltageIdDirect = _findSignal(signals, const [
      'max_voltage_cell_id_at_shutdown',
      'max_cell_voltage_id',
      'max_single_cell_voltage_id',
      'cell_max_voltage_id',
      'max_voltage_id',
    ], allowFaultAlarm: false, preferNonZero: true);
    final minCellVoltageIdDirect = _findSignal(signals, const [
      'min_voltage_cell_id_at_shutdown',
      'min_cell_voltage_id',
      'min_single_cell_voltage_id',
      'cell_min_voltage_id',
      'min_voltage_id',
    ], allowFaultAlarm: false, preferNonZero: true);

    final maxCellVoltageId = _intValue(maxCellVoltageIdDirect) ??
        (cellVoltageSignals.isNotEmpty
            ? _extractTrailingIndex(_signalName(maxCellVoltageSignal))
            : _intValue(_findSignal(signals, const [
                'max_voltage_cell_id_at_shutdown',
                'max_voltage_cell_id_at_alarm',
              ], allowFaultAlarm: true, preferNonZero: true)));

    final minCellVoltageId = _intValue(minCellVoltageIdDirect) ??
        (cellVoltageSignals.isNotEmpty
            ? _extractTrailingIndex(_signalName(minCellVoltageSignal))
            : _intValue(_findSignal(signals, const [
                'min_voltage_cell_id_at_shutdown',
                'min_voltage_cell_id_at_alarm',
              ], allowFaultAlarm: true, preferNonZero: true)));

    final measuredTempSignals = _measuredTemperatureSignals(signals);
    final maxTempDirect = _findSignal(signals, const [
      'max_cell_temperature_at_shutdown',
      'max_temperature',
      'max_temp',
      'max_cell_temperature',
      'battery_max_temperature',
      'maximum_temperature',
    ], allowFaultAlarm: false, preferNonZero: true);
    final minTempDirect = _findSignal(signals, const [
      'min_cell_temperature_at_shutdown',
      'min_temperature',
      'min_temp',
      'min_cell_temperature',
      'battery_min_temperature',
      'minimum_temperature',
    ], allowFaultAlarm: false, preferNonZero: true);

    final maxTempSignal = maxTempDirect ??
        (measuredTempSignals.isNotEmpty
            ? _maxByNumeric(measuredTempSignals)
            : _findSignal(signals, const [
                'max_cell_temperature_at_shutdown',
                'max_cell_temperature_at_alarm',
                'max_hv_box_temperature_at_shutdown',
                'max_hv_box_temperature_at_alarm',
              ], allowFaultAlarm: true, preferNonZero: true));

    final minTempSignal = minTempDirect ??
        (measuredTempSignals.isNotEmpty
            ? _minByNumeric(measuredTempSignals)
            : _findSignal(signals, const [
                'min_cell_temperature_at_shutdown',
                'min_cell_temperature_at_alarm',
              ], allowFaultAlarm: true, preferNonZero: true));

    final maxTempIdDirect = _findSignal(signals, const [
      'max_cell_temperature_point_id_at_shutdown',
      'max_temperature_id',
      'max_temp_id',
      'max_cell_temperature_id',
      'battery_max_temperature_id',
    ], allowFaultAlarm: false, preferNonZero: true);
    final minTempIdDirect = _findSignal(signals, const [
      'min_cell_temperature_point_id_at_shutdown',
      'min_temperature_id',
      'min_temp_id',
      'min_cell_temperature_id',
      'battery_min_temperature_id',
    ], allowFaultAlarm: false, preferNonZero: true);

    final maxTempId = _intValue(maxTempIdDirect) ??
        (measuredTempSignals.isNotEmpty
            ? _extractTrailingIndex(_signalName(maxTempSignal))
            : _intValue(_findSignal(signals, const [
                'max_cell_temperature_point_id_at_shutdown',
                'max_cell_temperature_point_id_at_alarm',
              ], allowFaultAlarm: true, preferNonZero: true)));

    final minTempId = _intValue(minTempIdDirect) ??
        (measuredTempSignals.isNotEmpty
            ? _extractTrailingIndex(_signalName(minTempSignal))
            : _intValue(_findSignal(signals, const [
                'min_cell_temperature_point_id_at_shutdown',
                'min_cell_temperature_point_id_at_alarm',
              ], allowFaultAlarm: true, preferNonZero: true)));

    final chargedSignal = _findSignal(signals, const [
      'monthly_cumulative_charge_energy',
      'yearly_cumulative_charge_energy',
      'total_energy_charged',
      'battery_total_energy_charged',
      'ac_cumulative_charge_energy',
      'dc_cumulative_charge_energy',
      'accumulated_charge_capacity',
      'total_cumulative_charge_capacity',
    ], allowFaultAlarm: false, preferNonZero: true);

    final dischargedSignal = _findSignal(signals, const [
      'monthly_cumulative_discharge_energy',
      'yearly_cumulative_discharge_energy',
      'total_energy_discharged',
      'battery_total_energy_discharged',
      'ac_cumulative_discharge_energy',
      'dc_cumulative_discharge_energy',
      'accumulated_discharge_capacity',
      'total_cumulative_discharge_capacity',
    ], allowFaultAlarm: false, preferNonZero: true);

    final systemStatus = _enumLabelOf(signals, const [
          'system_status',
          'bms_system_status',
          'status',
        ]) ??
        ((bmsTelemetry?['online'] == true || fallbackOnline) ? 'Online' : 'Offline');

    final explicitChargeDischarge = _enumLabelOf(signals, const [
      'charge_discharge_status',
      'charge_or_discharge_status',
      'operation_status',
    ]);
    final chargeDischarge = _normalizeChargeDischargeLabel(
          explicitChargeDischarge,
          _numericValue(packCurrentSignal),
        ) ??
        'Unavailable';

    final faultItems = _collectStateItems(signals, wantAlarm: false);
    final alarmItems = _collectStateItems(signals, wantAlarm: true);
    final thresholdItems = _collectThresholdItems(signals);

    final activeFaultCount = faultItems.where((e) => e.active).length;
    final activeAlarmCount = alarmItems.where((e) => e.active).length;

    final faultSummary = activeFaultCount > 0
        ? '$activeFaultCount active'
        : (faultItems.isEmpty ? 'Unavailable' : 'Normal');
    final alarmSummary = activeAlarmCount > 0
        ? '$activeAlarmCount active'
        : (alarmItems.isEmpty ? 'Unavailable' : 'Normal');

    return BmsSourceSnapshot(
      sourceId: source.sourceId,
      displayName: _professionalSourceName(source.displayName),
      host: source.host,
      port: source.port,
      online: (bmsTelemetry?['online'] == true) || fallbackOnline,
      systemStatusLabel: _professionalStateLabel(systemStatus),
      chargeDischargeStatusLabel: chargeDischarge,
      faultSummaryLabel: faultSummary,
      alarmSummaryLabel: alarmSummary,
      faultItems: faultItems,
      alarmItems: alarmItems,
      thresholdItems: thresholdItems,
      socPercent: soc,
      sohPercent: soh,
      packVoltageV: _numericValue(packVoltageSignal),
      packCurrentA: _numericValue(packCurrentSignal),
      clusterResistanceMilliOhm: _numericValue(resistanceSignal),
      maxCellVoltageMv: _numericValue(maxCellVoltageSignal),
      minCellVoltageMv: _numericValue(minCellVoltageSignal),
      maxCellVoltageId: maxCellVoltageId,
      minCellVoltageId: minCellVoltageId,
      maxTempC: _numericValue(maxTempSignal),
      minTempC: _numericValue(minTempSignal),
      maxTempId: maxTempId,
      minTempId: minTempId,
      totalEnergyCharged: _numericValue(chargedSignal),
      totalEnergyChargedUnit: _normalizedEnergyUnit(_unitOf(chargedSignal), _signalName(chargedSignal)),
      totalEnergyDischarged: _numericValue(dischargedSignal),
      totalEnergyDischargedUnit: _normalizedEnergyUnit(_unitOf(dischargedSignal), _signalName(dischargedSignal)),
    );
  }

  static Map<String, Map<String, dynamic>> _flattenSignals(Map<String, dynamic>? telemetry) {
    final out = <String, Map<String, dynamic>>{};
    if (telemetry == null) return out;

    void addFrom(dynamic section) {
      final map = (section as Map?)?.cast<String, dynamic>() ?? {};
      for (final entry in map.entries) {
        out[entry.key] = (entry.value as Map?)?.cast<String, dynamic>() ?? {};
      }
    }

    addFrom(telemetry['signals']);
    addFrom(telemetry['key_signals']);
    return out;
  }

  static List<Map<String, dynamic>> _measuredCellVoltageSignals(Map<String, Map<String, dynamic>> signals) {
    final out = <Map<String, dynamic>>[];
    for (final entry in signals.entries) {
      final key = entry.key.toLowerCase();
      final signal = entry.value;
      final category = (signal['category']?.toString() ?? '').toLowerCase();
      if (category == 'fault_alarm') continue;
      if (!RegExp(r'^cell_voltage_\d+$').hasMatch(key)) continue;
      final value = _numericValue(signal);
      if (value == null || value <= 0) continue;
      out.add(signal);
    }
    return out;
  }

  static List<Map<String, dynamic>> _measuredTemperatureSignals(Map<String, Map<String, dynamic>> signals) {
    final out = <Map<String, dynamic>>[];
    final patterns = <RegExp>[
      RegExp(r'^cell_temperature_\d+$'),
      RegExp(r'^battery_temperature_\d+$'),
      RegExp(r'^temperature_sensor_\d+$'),
      RegExp(r'^temp_sensor_\d+$'),
      RegExp(r'^module_temperature_\d+$'),
      RegExp(r'^pole_temperature_\d+$'),
      RegExp(r'^pole_temp_\d+$'),
      RegExp(r'^cluster_temperature_\d+$'),
    ];
    for (final entry in signals.entries) {
      final key = entry.key.toLowerCase();
      final signal = entry.value;
      final category = (signal['category']?.toString() ?? '').toLowerCase();
      if (category == 'fault_alarm') continue;
      if (!patterns.any((p) => p.hasMatch(key))) continue;
      final value = _numericValue(signal);
      if (value == null) continue;
      if (value < -50 || value > 150) continue;
      out.add(signal);
    }
    return out;
  }

  static Map<String, dynamic>? _findSignal(
    Map<String, Map<String, dynamic>> signals,
    List<String> names, {
    required bool allowFaultAlarm,
    required bool preferNonZero,
  }) {
    final exactCandidates = <Map<String, dynamic>>[];
    for (final name in names) {
      final signal = signals[name];
      if (signal == null) continue;
      if (!_isSignalAllowed(signal, allowFaultAlarm: allowFaultAlarm)) continue;
      if (_numericValue(signal) == null) continue;
      exactCandidates.add(signal);
    }
    final exact = _pickBestSignal(exactCandidates, preferNonZero: preferNonZero);
    if (exact != null) return exact;

    final fuzzyCandidates = <Map<String, dynamic>>[];
    for (final entry in signals.entries) {
      final key = entry.key.toLowerCase();
      if (!names.any((n) => key.contains(n.toLowerCase()))) continue;
      if (!_isSignalAllowed(entry.value, allowFaultAlarm: allowFaultAlarm)) continue;
      if (_numericValue(entry.value) == null) continue;
      fuzzyCandidates.add(entry.value);
    }
    return _pickBestSignal(fuzzyCandidates, preferNonZero: preferNonZero);
  }

  static double? _findMeasuredValue(
    Map<String, Map<String, dynamic>> signals,
    List<String> names, {
    required bool allowFaultAlarm,
  }) {
    return _numericValue(
      _findSignal(signals, names, allowFaultAlarm: allowFaultAlarm, preferNonZero: true),
    );
  }

  static Map<String, dynamic>? _pickBestSignal(List<Map<String, dynamic>> candidates, {required bool preferNonZero}) {
    if (candidates.isEmpty) return null;
    if (!preferNonZero) return candidates.first;
    for (final signal in candidates) {
      final value = _numericValue(signal);
      if (value != null && value.abs() > 0.0001) return signal;
    }
    return candidates.first;
  }

  static Map<String, dynamic>? _maxByNumeric(List<Map<String, dynamic>> items) {
    if (items.isEmpty) return null;
    items.sort((a, b) => (_numericValue(b) ?? double.negativeInfinity).compareTo(_numericValue(a) ?? double.negativeInfinity));
    return items.first;
  }

  static Map<String, dynamic>? _minByNumeric(List<Map<String, dynamic>> items) {
    if (items.isEmpty) return null;
    items.sort((a, b) => (_numericValue(a) ?? double.infinity).compareTo(_numericValue(b) ?? double.infinity));
    return items.first;
  }

  static bool _isSignalAllowed(Map<String, dynamic> signal, {required bool allowFaultAlarm}) {
    final category = (signal['category']?.toString() ?? '').toLowerCase();
    if (category.contains('fault_alarm') && !allowFaultAlarm) return false;
    return true;
  }

  static double? _numericValue(Map<String, dynamic>? signal) {
    if (signal == null) return null;
    final value = signal['value'];
    if (value is num) return value.toDouble();
    if (value is String) return double.tryParse(value);
    return null;
  }

  static int? _intValue(Map<String, dynamic>? signal) {
    final value = _numericValue(signal);
    if (value == null) return null;
    if (value.abs() < 0.0001) return null;
    return value.round();
  }

  static String? _unitOf(Map<String, dynamic>? signal) {
    final unit = signal?['unit']?.toString();
    if (unit == null || unit.trim().isEmpty) return null;
    return unit.trim();
  }

  static String? _signalName(Map<String, dynamic>? signal) {
    final name = signal?['name']?.toString();
    if (name == null || name.trim().isEmpty) return null;
    return name.trim();
  }

  static int? _extractTrailingIndex(String? signalName) {
    if (signalName == null) return null;
    final match = RegExp(r'_(\d+)$').firstMatch(signalName);
    if (match == null) return null;
    return int.tryParse(match.group(1)!);
  }

  static String? _normalizedEnergyUnit(String? unit, String? signalName) {
    final normalized = unit?.trim();
    if (normalized != null && normalized.isNotEmpty) {
      return normalized.toUpperCase() == 'AH' ? 'Ah' : normalized;
    }
    if (signalName == null) return null;
    return signalName.toLowerCase().contains('capacity') ? 'Ah' : null;
  }

  static String? _enumLabelOf(Map<String, Map<String, dynamic>> signals, List<String> names) {
    for (final name in names) {
      final signal = signals[name];
      if (signal == null) continue;
      final value = _numericValue(signal);
      final description = signal['description']?.toString() ?? '';
      final mapped = _mapEnumDescription(description, value);
      if (mapped != null) return mapped;
      final raw = signal['value']?.toString();
      if (raw != null && raw.isNotEmpty) return raw;
    }
    return null;
  }

  static String? _mapEnumDescription(String description, double? value) {
    if (description.isEmpty || value == null) return null;
    final pairs = description.split(';');
    for (final pair in pairs) {
      final idx = pair.indexOf(',');
      if (idx <= 0) continue;
      final k = double.tryParse(pair.substring(0, idx).trim());
      if (k == null) continue;
      if ((k - value).abs() < 0.001) {
        return pair.substring(idx + 1).trim();
      }
    }
    return null;
  }

  static String? _normalizeChargeDischargeLabel(String? label, double? current) {
    final normalized = label?.toLowerCase().trim();
    if (normalized == null || normalized.isEmpty) {
      return _deriveChargeDischarge(current);
    }
    if (normalized.contains('discharge')) return 'Discharge';
    if (normalized.contains('charge')) return 'Charge';
    if (normalized.contains('standby') || normalized.contains('idle') || normalized.contains('stop')) {
      final derived = _deriveChargeDischarge(current);
      return derived == 'Standby' ? 'Standby' : derived;
    }
    return _professionalStateLabel(label ?? 'Unavailable');
  }

  static String _deriveChargeDischarge(double? current) {
    if (current == null) return 'Unavailable';
    if (current > 0.5) return 'Discharge';
    if (current < -0.5) return 'Charge';
    return 'Standby';
  }

  static List<PcsFaultItem> _collectStateItems(
    Map<String, Map<String, dynamic>> signals, {
    required bool wantAlarm,
  }) {
    final items = <PcsFaultItem>[];
    final seen = <String>{};
    for (final entry in signals.entries) {
      final key = entry.key.toLowerCase();
      final signal = entry.value;
      final category = (signal['category']?.toString() ?? '').toLowerCase();
      final displayName = signal['display_name']?.toString() ?? _titleCase(entry.key);
      final description = signal['description']?.toString() ?? '';
      final searchText = '$key ${displayName.toLowerCase()} ${description.toLowerCase()}';
      if (!(category.contains('fault_alarm') ||
          searchText.contains('fault') ||
          searchText.contains('alarm') ||
          searchText.contains('protect') ||
          searchText.contains('warning') ||
          searchText.contains('level'))) {
        continue;
      }
      if (_isThresholdStyleSignal(searchText)) continue;

      final faultTokens = [
        ' fault',
        'fault ',
        'self-test',
        'self test',
        'sampling',
        'communication fault',
        'sensor fault',
        'chip fault',
        'contactor fault',
        'fuse fault',
        'functional safety fault',
        'protection',
        'trip',
      ];
      final warningTokens = [
        'alarm',
        'warning',
        'overvoltage',
        'undervoltage',
        'over-current',
        'overcurrent',
        'under-current',
        'undertemp',
        'under-temp',
        'overtemp',
        'over-temp',
        'too high',
        'too low',
        'imbalance',
        'diff',
        'level 1',
        'level 2',
        'level 3',
        'l1',
        'l2',
        'l3',
      ];

      final explicitFault = faultTokens.any(searchText.contains);
      final explicitAlarm = warningTokens.any(searchText.contains);
      final isFault = explicitFault;
      final isAlarm = explicitAlarm || (category.contains('fault_alarm') && !explicitFault);

      if (wantAlarm && !isAlarm) continue;
      if (!wantAlarm && !isFault) continue;

      final value = _numericValue(signal);
      final mapped = _mapEnumDescription(description, value) ??
          signal['value']?.toString() ??
          '--';
      final normalizedDisplay = _professionalSignalName(displayName);
      final dedupeKey = (wantAlarm ? 'alarm' : 'fault') + '::' + normalizedDisplay.toLowerCase();
      if (!seen.add(dedupeKey)) continue;
      final active = _isActive(value, mapped.toLowerCase());

      items.add(PcsFaultItem(
        signalName: entry.key,
        displayName: normalizedDisplay,
        category: wantAlarm ? 'alarm' : 'fault',
        stateLabel: _professionalStateLabel(mapped),
        active: active,
        quality: signal['quality']?.toString(),
        rawValue: value,
      ));
    }

    items.sort((a, b) {
      if (a.active != b.active) return a.active ? -1 : 1;
      return a.displayName.compareTo(b.displayName);
    });
    return items;
  }

  static List<PcsFaultItem> _collectThresholdItems(Map<String, Map<String, dynamic>> signals) {
    final items = <PcsFaultItem>[];
    for (final entry in signals.entries) {
      final key = entry.key.toLowerCase();
      final signal = entry.value;
      if (!_isThresholdStyleSignal(key)) continue;
      final value = _numericValue(signal);
      if (value == null) continue;
      final unit = _unitOf(signal);
      final label = unit == null || unit.isEmpty ? value.toStringAsFixed(1) : '${value.toStringAsFixed(1)} $unit';
      items.add(PcsFaultItem(
        signalName: entry.key,
        displayName: _professionalThresholdName(signal['display_name']?.toString() ?? _titleCase(entry.key)),
        category: 'threshold',
        stateLabel: label,
        active: false,
        quality: signal['quality']?.toString(),
        rawValue: value,
      ));
    }
    items.sort((a, b) => a.displayName.compareTo(b.displayName));
    return items;
  }

  static bool _isThresholdStyleSignal(String key) {
    const badTokens = [
      'limit',
      'recovery',
      'threshold',
      '_value',
      '_id',
      'point_id',
      'cell_id',
      'sensor_id',
      'pack_id',
      'diff_value',
      'resistance_value',
      'current_value',
      'voltage_value',
      'temperature_value',
      'temp_value',
      'shutdown_',
      '_shutdown',
      '_alarm_',
      '_at_alarm',
      '_at_shutdown',
      'setting',
    ];
    return badTokens.any(key.contains);
  }

  static bool _isActive(double? value, String normalizedLabel) {
    const inactiveWords = ['normal', 'no fault', 'no alarm', 'offline', 'standby', 'ok'];
    if (inactiveWords.any(normalizedLabel.contains)) return false;
    if (normalizedLabel.contains('invalid')) return false;
    if (value != null) return value != 0;
    return normalizedLabel.isNotEmpty && normalizedLabel != '--';
  }

  static String _professionalSourceName(String raw) {
    return raw
        .replaceAll('Chinese EMS 1', 'BESS EMS 1')
        .replaceAll('Chinese EMS 2', 'BESS EMS 2');
  }

  static String _professionalThresholdName(String raw) {
    var s = _professionalSignalName(raw);
    s = s.replaceAll('Alarm ', '');
    s = s.replaceAll('Recovery ', '');
    s = s.replaceAll('Shutdown ', 'Trip ');
    s = s.replaceAll('Value', 'Threshold');
    s = s.replaceAll('Point ID', 'Sensor / Cell ID');
    s = s.replaceAll('Diff', 'Difference');
    s = s.replaceAll('Over-High', 'High');
    return s;
  }

  static String _professionalSignalName(String raw) {
    var s = raw;
    const replacements = {
      'Rack Cell ': 'Cell ',
      'Battery Cell ': 'Cell ',
      'Battery Pack ': 'Pack ',
      'Battery Cluster ': 'Cluster ',
      'Temp ': 'Temperature ',
      'Over-Voltage': 'Overvoltage',
      'Under-Voltage': 'Undervoltage',
      'Over-Current': 'Overcurrent',
      'Pre-Charge': 'Precharge',
      'SW Fault-': '',
      'HW Fault-': '',
      'ARM ': '',
      'EMS ': '',
      'RTC ': 'RTC ',
      'Voltage Diff': 'Voltage Imbalance',
      'Temp Diff': 'Temperature Imbalance',
      'HV Box': 'HV Box',
      'BAU': 'BAU',
      'BCU': 'BCU',
      'BMU': 'BMU',
    };
    replacements.forEach((k, v) => s = s.replaceAll(k, v));
    s = s.replaceAll('(Critical Alarm)', '(Critical)');
    s = s.replaceAll('(Early Warning)', '(Warning)');
    s = s.replaceAll('Level 1', 'L1');
    s = s.replaceAll('Level 2', 'L2');
    s = s.replaceAll('Level 3', 'L3');
    s = s.replaceAll('  ', ' ').trim();
    return s;
  }

  static String _professionalStateLabel(String raw) {
    final lower = raw.toLowerCase().trim();
    if (lower == 'normal') return 'Normal';
    if (lower == 'fault') return 'Fault Active';
    if (lower == 'alarm') return 'Alarm Active';
    if (lower == 'warning') return 'Warning Active';
    if (lower == 'invalid') return 'Invalid';
    if (lower == 'offline') return 'Offline';
    if (lower == 'online') return 'Online';
    return raw
        .replaceAll('fault', 'Fault')
        .replaceAll('alarm', 'Alarm')
        .replaceAll('warning', 'Warning');
  }

  static String _titleCase(String text) => text
      .replaceAll('_', ' ')
      .split(' ')
      .where((e) => e.isNotEmpty)
      .map((e) => e[0].toUpperCase() + e.substring(1))
      .join(' ');
}
