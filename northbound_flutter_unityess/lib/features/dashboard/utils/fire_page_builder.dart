import '../models/fire_source_snapshot.dart';
import '../models/pcs_fault_item.dart';
import '../models/source_summary.dart';

class FirePageBuilder {
  const FirePageBuilder._();

  static FireSourceSnapshot buildForSource({
    required SourceSummary source,
    Map<String, dynamic>? fireTelemetry,
    bool fallbackOnline = false,
  }) {
    final signals = _flattenSignals(fireTelemetry);

    final communicationStatus = _enumLabelOf(signals, const [
          'communication_status',
          'communication',
          'online_point',
        ]) ??
        (((fireTelemetry?['online'] == true) || fallbackOnline) ? 'Online' : 'Offline');

    final faultItems = _collectStateItems(signals, wantAlarm: false);
    final alarmItems = _collectStateItems(signals, wantAlarm: true);
    final configItems = _collectConfigItems(signals);

    final activeFaults = faultItems.where((e) => e.active).length;
    final activeAlarms = alarmItems.where((e) => e.active).length;

    return FireSourceSnapshot(
      sourceId: source.sourceId,
      displayName: source.displayName,
      host: source.host,
      port: source.port,
      online: (fireTelemetry?['online'] == true) || fallbackOnline,
      communicationStatusLabel: _professionalStateLabel(communicationStatus),
      faultSummaryLabel: activeFaults > 0 ? '$activeFaults active' : (faultItems.isEmpty ? 'Unavailable' : 'Normal'),
      alarmSummaryLabel: activeAlarms > 0 ? '$activeAlarms active' : (alarmItems.isEmpty ? 'Unavailable' : 'Normal'),
      faultItems: faultItems,
      alarmItems: alarmItems,
      configItems: configItems,
      temperatureC: _valueOf(signals, const ['temperature_value', 'current_temperature', 'temperature']),
      co1: _valueOf(signals, const ['co1', 'co_1']),
      co2: _valueOf(signals, const ['co2', 'co_2']),
      co3: _valueOf(signals, const ['co3', 'co_3']),
      activationStatusLabel: _maybeLabel(signals, const ['fault_activation', 'alarm_activation', 'activation_status']),
      feedbackStatusLabel: _maybeLabel(signals, const ['fault_feedback', 'alarm_feedback', 'feedback_status']),
      infraredHighLevel: _valueOf(signals, const ['infrared_high_level']),
      infraredLowLevel: _valueOf(signals, const ['infrared_low_level']),
      fanDamperAlarmLabel: _maybeLabel(signals, const ['fan_damper_control_module_alarm']),
      fanDamperStatusLabel: _maybeLabel(signals, const ['fan_damper_control_module_status']),
      audibleVisualAlarmLabel: _maybeLabel(signals, const ['audible_visual_alarm_module_alarm']),
      audibleVisualStatusLabel: _maybeLabel(signals, const ['audible_visual_alarm_module_status']),
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
    final signal = _findSignal(signals, names, preferNonZero: false);
    return _numericValue(signal);
  }

  static String? _maybeLabel(Map<String, Map<String, dynamic>> signals, List<String> names) {
    final raw = _enumLabelOf(signals, names);
    return raw == null ? null : _professionalStateLabel(raw);
  }

  static Map<String, dynamic>? _findSignal(Map<String, Map<String, dynamic>> signals, List<String> names, {required bool preferNonZero}) {
    final exact = <Map<String, dynamic>>[];
    for (final name in names) {
      final signal = signals[name];
      if (signal == null) continue;
      exact.add(signal);
    }
    final pickedExact = _pickBestSignal(exact, preferNonZero: preferNonZero);
    if (pickedExact != null) return pickedExact;

    final fuzzy = <Map<String, dynamic>>[];
    for (final entry in signals.entries) {
      final key = entry.key.toLowerCase();
      if (!names.any((n) => key.contains(n.toLowerCase()))) continue;
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

  static double? _numericValue(Map<String, dynamic>? signal) {
    if (signal == null) return null;
    final value = signal['value'];
    if (value is num) return value.toDouble();
    if (value is String) return double.tryParse(value);
    return null;
  }

  static String? _enumLabelOf(Map<String, Map<String, dynamic>> signals, List<String> names) {
    final signal = _findSignal(signals, names, preferNonZero: false);
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

      if (_isConfigStyleSignal(search)) continue;
      final isAlarm = search.contains('alarm') || search.contains('warning') || search.contains('activation');
      final isFault = search.contains('fault') || search.contains('feedback') || search.contains('communication') || category.contains('fault_alarm');
      if (wantAlarm && !isAlarm) continue;
      if (!wantAlarm && !isFault) continue;

      final value = _numericValue(signal);
      final state = _mapEnumDescription(description, value) ?? signal['value']?.toString() ?? '--';
      final normalizedName = _professionalSignalName(displayName);
      final dedupe = '${wantAlarm ? 'alarm' : 'fault'}::$normalizedName';
      if (!seen.add(dedupe)) continue;

      items.add(PcsFaultItem(
        signalName: entry.key,
        displayName: normalizedName,
        category: wantAlarm ? 'alarm' : 'fault',
        stateLabel: _professionalStateLabel(state),
        active: _isActive(value, state.toLowerCase()),
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
      if (!_isConfigStyleSignal(key)) continue;
      final signal = entry.value;
      final value = _numericValue(signal);
      final unit = signal['unit']?.toString();
      final state = value != null
          ? ((unit == null || unit.isEmpty) ? value.toStringAsFixed(1) : '${value.toStringAsFixed(1)} $unit')
          : (signal['value']?.toString() ?? '--');
      items.add(PcsFaultItem(
        signalName: entry.key,
        displayName: _professionalSignalName(signal['display_name']?.toString() ?? _titleCase(entry.key)),
        category: 'config',
        stateLabel: state,
        active: false,
        quality: signal['quality']?.toString(),
        rawValue: value,
      ));
    }
    items.sort((a, b) => a.displayName.compareTo(b.displayName));
    return items;
  }

  static bool _isConfigStyleSignal(String key) {
    const tokens = ['threshold', 'limit', 'setting', 'setpoint', 'recovery'];
    return tokens.any(key.contains);
  }

  static bool _isActive(double? value, String normalizedState) {
    const inactive = ['normal', 'no fault', 'no alarm', 'offline', 'off', 'stopped', 'stop', 'closed'];
    if (inactive.any(normalizedState.contains)) return false;
    if (normalizedState.contains('invalid') || normalizedState == '--') return false;
    if (value != null) return value != 0;
    return normalizedState.isNotEmpty;
  }

  static String _professionalSignalName(String raw) {
    var s = raw.replaceAll('_', ' ');
    s = s.replaceAll('Fault ', '');
    s = s.replaceAll('Alarm ', '');
    s = s.replaceAll('CO', 'CO');
    s = s.replaceAll('Infrared', 'Infrared');
    s = s.replaceAll('  ', ' ').trim();
    return s;
  }

  static String _professionalStateLabel(String raw) {
    final lower = raw.toLowerCase().trim();
    if (lower == 'normal') return 'Normal';
    if (lower == 'online') return 'Online';
    if (lower == 'offline') return 'Offline';
    if (lower == 'on') return 'On';
    if (lower == 'off') return 'Off';
    if (lower == 'running') return 'Running';
    if (lower == 'stopped') return 'Stopped';
    return raw;
  }

  static String _titleCase(String text) => text
      .replaceAll('_', ' ')
      .split(' ')
      .where((e) => e.isNotEmpty)
      .map((e) => e[0].toUpperCase() + e.substring(1))
      .join(' ');
}
