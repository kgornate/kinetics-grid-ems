
import '../models/pcs_fault_item.dart';
import '../models/source_summary.dart';
import '../models/utility_meter_source_snapshot.dart';

class UtilityMeterPageBuilder {
  const UtilityMeterPageBuilder._();

  static UtilityMeterSourceSnapshot buildForSource({
    required SourceSummary source,
    Map<String, dynamic>? meterTelemetry,
    bool fallbackOnline = false,
  }) {
    final signals = _flattenSignals(meterTelemetry);

    final statusLabel = _enumLabelOf(signals, const [
          'status',
          'meter_status',
          'communication_status',
          'online_point',
        ]) ??
        (((meterTelemetry?['online'] == true) || fallbackOnline) ? 'Online' : 'Offline');

    final operatingMode = _enumLabelOf(signals, const [
          'operating_mode',
          'operation_mode',
          'meter_mode',
          'work_mode',
        ]) ??
        'Live Monitoring';

    final faultItems = _collectStateItems(signals, wantAlarm: false);
    final alarmItems = _collectStateItems(signals, wantAlarm: true);
    final configItems = _collectConfigItems(signals);

    final activeFaults = faultItems.where((e) => e.active).length;
    final activeAlarms = alarmItems.where((e) => e.active).length;

    return UtilityMeterSourceSnapshot(
      sourceId: source.sourceId,
      displayName: source.displayName,
      host: source.host,
      port: source.port,
      online: (meterTelemetry?['online'] == true) || fallbackOnline,
      statusLabel: _professionalStateLabel(statusLabel),
      operatingModeLabel: _professionalStateLabel(operatingMode),
      faultSummaryLabel: activeFaults > 0 ? '$activeFaults active' : (faultItems.isEmpty ? 'Normal' : 'Normal'),
      alarmSummaryLabel: activeAlarms > 0 ? '$activeAlarms active' : (alarmItems.isEmpty ? 'Normal' : 'Normal'),
      faultItems: faultItems,
      alarmItems: alarmItems,
      configItems: configItems,
      frequencyHz: _valueOf(signals, const [
        'grid_frequency',
        'frequency',
        'mains_frequency',
        'metering_frequency',
      ]),
      activePowerKw: _valueOf(signals, const [
        'grid_current_total_power',
        'mains_current_total_power',
        'metering_current_total_power',
        'active_power',
        'total_active_power',
      ]),
      reactivePowerKvar: _valueOf(signals, const [
        'current_reactive_power',
        'reactive_power',
        'total_reactive_power',
      ]),
      powerFactor: _valueOf(signals, const [
        'power_factor',
        'current_power_factor',
        'total_power_factor',
      ]),
      lineVoltageV: _valueOf(signals, const [
        'line_voltage',
        'grid_line_voltage',
        'mains_line_voltage',
        'voltage_ab',
        'line_to_line_voltage',
      ]),
      lineCurrentA: _valueOf(signals, const [
        'line_current',
        'grid_line_current',
        'mains_line_current',
        'current_a',
        'total_current',
      ]),
      importEnergyKwh: _valueOf(signals, const [
        'import_energy',
        'grid_import_energy',
        'positive_active_energy',
        'energy_import',
      ]),
      exportEnergyKwh: _valueOf(signals, const [
        'export_energy',
        'grid_export_energy',
        'negative_active_energy',
        'energy_export',
      ]),
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

  static List<PcsFaultItem> _collectStateItems(
    Map<String, Map<String, dynamic>> signals, {
    required bool wantAlarm,
  }) {
    final items = <PcsFaultItem>[];
    final seen = <String>{};
    for (final entry in signals.entries) {
      final key = entry.key.toLowerCase();
      final value = entry.value;
      final category = (value['category']?.toString().toLowerCase() ?? '');
      final displayName = _displayName(entry.key, value);
      final stateLabel = _stateLabel(value);
      final active = _isActive(value);

      final thresholdish = key.contains('threshold') ||
          key.contains('limit') ||
          key.contains('setting') ||
          key.contains('recovery');
      if (thresholdish) continue;

      final alarmLike = category.contains('alarm') ||
          key.contains('alarm') ||
          displayName.toLowerCase().contains('alarm') ||
          displayName.toLowerCase().contains('warning');

      final faultLike = category.contains('fault') ||
          key.contains('fault') ||
          displayName.toLowerCase().contains('fault') ||
          displayName.toLowerCase().contains('trip');

      if (wantAlarm && !alarmLike) continue;
      if (!wantAlarm && !(faultLike && !alarmLike)) continue;

      if (!seen.add(entry.key)) continue;
      items.add(PcsFaultItem(
        signalName: entry.key,
        displayName: displayName,
        category: wantAlarm ? 'alarm' : 'fault',
        stateLabel: stateLabel,
        active: active,
        quality: value['quality']?.toString(),
        rawValue: _numericValue(value),
      ));
    }
    items.sort((a, b) {
      if (a.active == b.active) return a.displayName.compareTo(b.displayName);
      return a.active ? -1 : 1;
    });
    return items;
  }

  static List<PcsFaultItem> _collectConfigItems(Map<String, Map<String, dynamic>> signals) {
    final items = <PcsFaultItem>[];
    for (final entry in signals.entries) {
      final key = entry.key.toLowerCase();
      final value = entry.value;
      if (!(key.contains('limit') ||
          key.contains('setting') ||
          key.contains('threshold') ||
          key.contains('recovery'))) {
        continue;
      }
      items.add(PcsFaultItem(
        signalName: entry.key,
        displayName: _displayName(entry.key, value),
        category: 'config',
        stateLabel: _stateLabel(value),
        active: false,
        quality: value['quality']?.toString(),
        rawValue: _numericValue(value),
      ));
    }
    items.sort((a, b) => a.displayName.compareTo(b.displayName));
    return items;
  }

  static double? _valueOf(Map<String, Map<String, dynamic>> signals, List<String> names) {
    final signal = _findSignal(signals, names, preferNonZero: true);
    return _numericValue(signal);
  }

  static Map<String, dynamic>? _findSignal(Map<String, Map<String, dynamic>> signals, List<String> names, {required bool preferNonZero}) {
    for (final name in names) {
      if (signals.containsKey(name)) {
        final s = signals[name]!;
        final n = _numericValue(s);
        if (!preferNonZero || (n != null && n != 0)) return s;
      }
    }
    for (final entry in signals.entries) {
      final key = entry.key.toLowerCase();
      if (names.any((n) => key.contains(n.toLowerCase()))) {
        final n = _numericValue(entry.value);
        if (!preferNonZero || (n != null && n != 0)) return entry.value;
      }
    }
    for (final entry in signals.entries) {
      final key = entry.key.toLowerCase();
      if (names.any((n) => key.contains(n.toLowerCase()))) {
        return entry.value;
      }
    }
    return null;
  }

  static String? _enumLabelOf(Map<String, Map<String, dynamic>> signals, List<String> names) {
    final signal = _findSignal(signals, names, preferNonZero: false);
    if (signal == null) return null;
    final label = signal['enum_label']?.toString();
    if (label != null && label.trim().isNotEmpty) return label;
    return signal['display_value']?.toString();
  }

  static double? _numericValue(Map<String, dynamic>? signal) {
    if (signal == null) return null;
    final value = signal['value'];
    if (value is num) return value.toDouble();
    if (value is String) return double.tryParse(value);
    return null;
  }

  static String _stateLabel(Map<String, dynamic> signal) {
    final enumLabel = signal['enum_label']?.toString();
    if (enumLabel != null && enumLabel.trim().isNotEmpty) {
      return _professionalStateLabel(enumLabel);
    }
    final displayValue = signal['display_value']?.toString();
    if (displayValue != null && displayValue.trim().isNotEmpty) {
      return displayValue;
    }
    final numeric = _numericValue(signal);
    if (numeric != null) return numeric.toStringAsFixed(numeric % 1 == 0 ? 0 : 1);
    return 'Unavailable';
  }

  static bool _isActive(Map<String, dynamic> signal) {
    final value = signal['value'];
    if (value is bool) return value;
    final numeric = _numericValue(signal);
    return numeric != null && numeric > 0;
  }

  static String _displayName(String key, Map<String, dynamic> signal) {
    final display = signal['display_name']?.toString();
    if (display != null && display.trim().isNotEmpty) return display;
    return key
        .replaceAll('_', ' ')
        .split(' ')
        .where((e) => e.isNotEmpty)
        .map((e) => e[0].toUpperCase() + e.substring(1))
        .join(' ');
  }

  static String _professionalStateLabel(String label) {
    final lower = label.toLowerCase().trim();
    if (lower == '0') return 'Inactive';
    if (lower == '1') return 'Active';
    if (lower == 'ok') return 'Normal';
    if (lower == 'na') return 'Unavailable';
    return label;
  }
}
