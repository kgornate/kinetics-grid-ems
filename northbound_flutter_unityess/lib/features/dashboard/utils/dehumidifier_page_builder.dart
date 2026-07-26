import '../models/dehumidifier_source_snapshot.dart';
import '../models/pcs_fault_item.dart';
import '../models/source_summary.dart';

class DehumidifierPageBuilder {
  const DehumidifierPageBuilder._();

  static DehumidifierSourceSnapshot buildForSource({
    required SourceSummary source,
    Map<String, dynamic>? dehumidifierTelemetry,
    bool fallbackOnline = false,
  }) {
    final signals = _flattenSignals(dehumidifierTelemetry);

    final onlinePointLabel = _enumLabelOf(signals, const [
          'online_point',
          'online_status',
          'online',
        ]) ??
        (((dehumidifierTelemetry?['online'] == true) || fallbackOnline) ? 'Online' : 'Offline');

    final operatingMode = _enumLabelOf(signals, const [
          'operating_mode',
          'operation_mode',
          'mode',
        ]) ??
        'Unavailable';

    final tempControlStatus = _enumLabelOf(signals, const [
          'temperature_control_status',
          'temp_control_status',
        ]) ??
        'Unavailable';

    final dehumStatus = _enumLabelOf(signals, const [
          'dehumidification_status',
          'dehumidifier_status',
          'status',
        ]) ??
        'Unavailable';

    final alarmStatus = _enumLabelOf(signals, const [
          'alarm_status',
          'alarm',
        ]) ??
        'Unavailable';

    final humidityControlMode = _enumLabelOf(signals, const [
          'humidity_control_mode',
          'humidity_mode',
          'humidity_control',
        ]) ??
        'Unavailable';

    final dehumSwitch = _enumLabelOf(signals, const [
          'dehumidification_switch_control_bit',
          'dehumidification_switch',
          'switch_control_bit',
        ]) ??
        'Unavailable';

    final faultItems = _collectStateItems(signals, wantAlarm: false);
    final alarmItems = _collectStateItems(signals, wantAlarm: true);
    final configItems = _collectConfigItems(signals);

    final activeFaults = faultItems.where((e) => e.active).length;
    final activeAlarms = alarmItems.where((e) => e.active).length;

    return DehumidifierSourceSnapshot(
      sourceId: source.sourceId,
      displayName: source.displayName,
      host: source.host,
      port: source.port,
      online: (dehumidifierTelemetry?['online'] == true) || fallbackOnline,
      onlinePointLabel: _professionalStateLabel(onlinePointLabel),
      operatingModeLabel: _professionalStateLabel(operatingMode),
      temperatureControlStatusLabel: _professionalStateLabel(tempControlStatus),
      dehumidificationStatusLabel: _professionalStateLabel(dehumStatus),
      alarmStatusLabel: _professionalStateLabel(alarmStatus),
      humidityControlModeLabel: _professionalStateLabel(humidityControlMode),
      dehumidificationSwitchLabel: _professionalStateLabel(dehumSwitch),
      faultSummaryLabel: activeFaults > 0 ? '$activeFaults active' : (faultItems.isEmpty ? 'Unavailable' : 'Normal'),
      alarmSummaryLabel: activeAlarms > 0 ? '$activeAlarms active' : (alarmItems.isEmpty ? 'Unavailable' : 'Normal'),
      faultItems: faultItems,
      alarmItems: alarmItems,
      configItems: configItems,
      currentTemperatureC: _valueOf(signals, const ['current_temperature', 'temperature', 'current_temp']),
      currentHumidityPct: _valueOf(signals, const ['current_humidity', 'humidity', 'humidity_value']),
      controllerInternalTemperatureC: _valueOf(signals, const ['controller_internal_temperature', 'internal_temperature', 'controller_temp']),
      temperatureSettingC: _valueOf(signals, const ['temperature_setting', 'temp_setting', 'temperature_setpoint']),
      temperatureHysteresisC: _valueOf(signals, const ['temperature_hysteresis', 'temp_hysteresis']),
      humiditySettingPct: _valueOf(signals, const ['humidity_setting', 'humidity_setpoint']),
      humidityHysteresisPct: _valueOf(signals, const ['humidity_hysteresis']),
      communicationBaudRate: _valueOf(signals, const ['communication_baud_rate', 'baud_rate']),
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

  static double? _valueOf(Map<String, Map<String, dynamic>> signals, List<String> names) {
    final signal = _findSignal(signals, names, allowFaultAlarm: true, preferNonZero: false);
    return _numericValue(signal);
  }

  static Map<String, dynamic>? _findSignal(
    Map<String, Map<String, dynamic>> signals,
    List<String> names, {
    required bool allowFaultAlarm,
    required bool preferNonZero,
  }) {
    final exact = <Map<String, dynamic>>[];
    for (final name in names) {
      final signal = signals[name];
      if (signal == null) continue;
      if (!_isSignalAllowed(signal, allowFaultAlarm: allowFaultAlarm)) continue;
      if (_numericValue(signal) == null && (signal['value']?.toString().isEmpty ?? true)) continue;
      exact.add(signal);
    }
    final pickedExact = _pickBestSignal(exact, preferNonZero: preferNonZero);
    if (pickedExact != null) return pickedExact;

    final fuzzy = <Map<String, dynamic>>[];
    for (final entry in signals.entries) {
      final key = entry.key.toLowerCase();
      if (!names.any((n) => key.contains(n.toLowerCase()))) continue;
      if (!_isSignalAllowed(entry.value, allowFaultAlarm: allowFaultAlarm)) continue;
      fuzzy.add(entry.value);
    }
    return _pickBestSignal(fuzzy, preferNonZero: preferNonZero);
  }

  static Map<String, dynamic>? _pickBestSignal(List<Map<String, dynamic>> items, {required bool preferNonZero}) {
    if (items.isEmpty) return null;
    if (!preferNonZero) return items.first;
    for (final item in items) {
      final n = _numericValue(item);
      if (n != null && n.abs() > 0.0001) return item;
    }
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

  static String? _enumLabelOf(Map<String, Map<String, dynamic>> signals, List<String> names) {
    final signal = _findSignal(signals, names, allowFaultAlarm: true, preferNonZero: false);
    if (signal == null) return null;
    final value = _numericValue(signal);
    final description = signal['description']?.toString() ?? '';
    final mapped = _mapEnumDescription(description, value);
    if (mapped != null) return mapped;
    final raw = signal['value']?.toString();
    return raw == null || raw.isEmpty ? null : raw;
  }

  static String? _mapEnumDescription(String description, double? value) {
    if (description.isEmpty || value == null) return null;
    for (final pair in description.split(';')) {
      final idx = pair.indexOf(',');
      if (idx <= 0) continue;
      final k = double.tryParse(pair.substring(0, idx).trim());
      if (k == null) continue;
      if ((k - value).abs() < 0.001) return pair.substring(idx + 1).trim();
    }
    return null;
  }

  static List<PcsFaultItem> _collectStateItems(Map<String, Map<String, dynamic>> signals, {required bool wantAlarm}) {
    final items = <PcsFaultItem>[];
    final seen = <String>{};

    for (final entry in signals.entries) {
      final key = entry.key.toLowerCase();
      final signal = entry.value;
      final displayName = signal['display_name']?.toString() ?? _titleCase(entry.key);
      final description = signal['description']?.toString() ?? '';
      final category = (signal['category']?.toString() ?? '').toLowerCase();
      final search = '$key ${displayName.toLowerCase()} ${description.toLowerCase()}';

      final thresholdLike = _isConfigStyleSignal(search);
      if (thresholdLike) continue;

      final isAlarm = search.contains('alarm') || search.contains('warning');
      final isFault = search.contains('fault') || search.contains('protect') || search.contains('communication status') || category.contains('fault_alarm');
      if (wantAlarm && !isAlarm) continue;
      if (!wantAlarm && !isFault) continue;

      final value = _numericValue(signal);
      final state = _mapEnumDescription(description, value) ?? signal['value']?.toString() ?? '--';
      final active = _isActive(value, state.toLowerCase());
      final normalizedName = _professionalSignalName(displayName);
      final dedupe = '${wantAlarm ? 'alarm' : 'fault'}::$normalizedName';
      if (!seen.add(dedupe)) continue;

      items.add(PcsFaultItem(
        signalName: entry.key,
        displayName: normalizedName,
        category: wantAlarm ? 'alarm' : 'fault',
        stateLabel: _professionalStateLabel(state),
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

  static List<PcsFaultItem> _collectConfigItems(Map<String, Map<String, dynamic>> signals) {
    final items = <PcsFaultItem>[];
    for (final entry in signals.entries) {
      final key = entry.key.toLowerCase();
      final signal = entry.value;
      if (!_isConfigStyleSignal(key)) continue;
      final value = _numericValue(signal);
      if (value == null && (signal['value']?.toString().isEmpty ?? true)) continue;
      final unit = signal['unit']?.toString();
      final label = value != null
          ? ((unit == null || unit.isEmpty) ? value.toStringAsFixed(1) : '${value.toStringAsFixed(1)} $unit')
          : (signal['value']?.toString() ?? '--');
      items.add(PcsFaultItem(
        signalName: entry.key,
        displayName: _professionalSignalName(signal['display_name']?.toString() ?? _titleCase(entry.key)),
        category: 'config',
        stateLabel: label,
        active: false,
        quality: signal['quality']?.toString(),
        rawValue: value,
      ));
    }
    items.sort((a, b) => a.displayName.compareTo(b.displayName));
    return items;
  }

  static bool _isConfigStyleSignal(String key) {
    const tokens = [
      'setting',
      'setpoint',
      'hysteresis',
      'limit',
      'threshold',
      'recovery',
      'baud',
      'switch control',
      'switch_control',
      'control bit',
      'control_bit',
      'mode setting',
    ];
    return tokens.any(key.contains);
  }

  static bool _isActive(double? value, String normalizedState) {
    const inactive = ['normal', 'no fault', 'no alarm', 'offline', 'off', 'stopped', 'stop', 'closed', 'auto'];
    if (inactive.any(normalizedState.contains)) return false;
    if (normalizedState.contains('invalid') || normalizedState == '--') return false;
    if (value != null) return value != 0;
    return normalizedState.isNotEmpty;
  }

  static String _professionalSignalName(String raw) {
    var s = raw.replaceAll('_', ' ');
    s = s.replaceAll('Current ', 'Current ');
    s = s.replaceAll('Temp ', 'Temperature ');
    s = s.replaceAll('Dehumidification', 'Dehumidification');
    s = s.replaceAll('Control Bit', 'Control');
    s = s.replaceAll('  ', ' ').trim();
    return s;
  }

  static String _professionalStateLabel(String raw) {
    final lower = raw.toLowerCase().trim();
    if (lower == 'normal') return 'Normal';
    if (lower == 'on') return 'On';
    if (lower == 'off') return 'Off';
    if (lower == 'online') return 'Online';
    if (lower == 'offline') return 'Offline';
    if (lower == 'auto') return 'Auto';
    if (lower == 'manual') return 'Manual';
    return raw;
  }

  static String _titleCase(String text) => text
      .replaceAll('_', ' ')
      .split(' ')
      .where((e) => e.isNotEmpty)
      .map((e) => e[0].toUpperCase() + e.substring(1))
      .join(' ');
}
