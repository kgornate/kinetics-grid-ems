import '../models/liquid_cooling_source_snapshot.dart';
import '../models/pcs_fault_item.dart';
import '../models/source_summary.dart';

class LiquidCoolingPageBuilder {
  const LiquidCoolingPageBuilder._();

  static LiquidCoolingSourceSnapshot buildForSource({
    required SourceSummary source,
    Map<String, dynamic>? coolingTelemetry,
    bool fallbackOnline = false,
  }) {
    final signals = _flattenSignals(coolingTelemetry);

    final powerStatus = _enumLabelOf(signals, const [
          'power_on_off',
          'power_status',
          'on_off',
          'online_point',
        ]) ??
        ((coolingTelemetry?['online'] == true || fallbackOnline) ? 'Online' : 'Offline');

    final operatingMode = _enumLabelOf(signals, const [
          'operating_mode',
          'operation_mode',
          'unit_operation_mode',
          'unit_control_mode',
          'monitor_mode',
        ]) ??
        'Unavailable';

    final faultItems = _collectStateItems(signals, wantAlarm: false);
    final alarmItems = _collectStateItems(signals, wantAlarm: true);

    final alarmSummary = alarmItems.any((e) => e.active)
        ? '${alarmItems.where((e) => e.active).length} active'
        : (alarmItems.isEmpty ? 'Unavailable' : 'Normal');
    final faultSummary = faultItems.any((e) => e.active)
        ? '${faultItems.where((e) => e.active).length} active'
        : (faultItems.isEmpty ? 'Unavailable' : 'Normal');

    return LiquidCoolingSourceSnapshot(
      sourceId: source.sourceId,
      displayName: source.displayName,
      host: source.host,
      port: source.port,
      online: (coolingTelemetry?['online'] == true) || fallbackOnline,
      powerStatusLabel: powerStatus,
      operatingModeLabel: operatingMode,
      alarmSummaryLabel: alarmSummary,
      faultSummaryLabel: faultSummary,
      faultItems: faultItems,
      alarmItems: alarmItems,
      coolingSetTempC: _valueOf(signals, const ['cooling_set_temperature']),
      heatingSetTempC: _valueOf(signals, const ['heating_set_temperature']),
      inletWaterTempC: _valueOf(signals, const ['inlet_water_temp', 'inlet_water_temperature']),
      outletWaterTempC: _valueOf(signals, const ['outlet_water_temp', 'outlet_water_temperature']),
      inletWaterPressureBar: _valueOf(signals, const ['inlet_water_press', 'inlet_water_pressure']),
      outletWaterPressureBar: _valueOf(signals, const ['outlet_water_press', 'outlet_water_pressure']),
      outletHighTempAlarmValueC: _valueOf(signals, const ['outlet_high_temp_alarm_value']),
      outletLowTempAlarmValueC: _valueOf(signals, const ['outlet_low_temp_alarm_value']),
      outletHighPressureAlarmValueBar: _valueOf(signals, const ['outlet_high_pressure_alarm_value']),
      inletLowPressureAlarmValueBar: _valueOf(signals, const ['inlet_low_pressure_alarm_value']),
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
    for (final entry in signals.entries) {
      final key = entry.key.toLowerCase();
      final signal = entry.value;
      final category = (signal['category']?.toString() ?? '').toLowerCase();

      if (!(category.contains('fault_alarm') ||
          key.contains('fault') ||
          key.contains('alarm') ||
          key.contains('warning') ||
          key.contains('protect'))) {
        continue;
      }

      final isAlarm = key.contains('alarm') || key.contains('warning');
      final isFault = key.contains('fault') || key.contains('protect') || (!isAlarm && category.contains('fault_alarm'));
      if (wantAlarm && !isAlarm) continue;
      if (!wantAlarm && !isFault) continue;

      final value = _numericValue(signal);
      final stateLabel = _enumLabelOf({entry.key: signal}, [entry.key]) ??
          signal['value']?.toString() ??
          '--';
      final displayName = signal['display_name']?.toString() ?? _titleCase(entry.key);
      final active = _isActive(value, stateLabel.toLowerCase());

      items.add(PcsFaultItem(
        signalName: entry.key,
        displayName: displayName,
        category: wantAlarm ? 'alarm' : 'fault',
        stateLabel: stateLabel,
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

  static bool _isActive(double? value, String normalizedLabel) {
    const inactiveWords = ['normal', 'no fault', 'no alarm', 'offline', 'stop', 'stopped', 'closed'];
    if (inactiveWords.contains(normalizedLabel)) return false;
    if (normalizedLabel.contains('invalid')) return false;
    if (value != null) return value != 0;
    return normalizedLabel.isNotEmpty && normalizedLabel != '--';
  }

  static double? _valueOf(Map<String, Map<String, dynamic>> signals, List<String> names) {
    for (final name in names) {
      final signal = signals[name];
      if (signal == null) continue;
      final value = _numericValue(signal);
      if (value != null) return value;
    }
    for (final entry in signals.entries) {
      final key = entry.key.toLowerCase();
      if (names.any((n) => key.contains(n.toLowerCase()))) {
        final value = _numericValue(entry.value);
        if (value != null) return value;
      }
    }
    return null;
  }

  static double? _numericValue(Map<String, dynamic>? signal) {
    if (signal == null) return null;
    final value = signal['value'];
    if (value is num) return value.toDouble();
    if (value is String) return double.tryParse(value);
    return null;
  }

  static String? _enumLabelOf(Map<String, Map<String, dynamic>> signals, List<String> names) {
    for (final name in names) {
      final signal = signals[name];
      if (signal == null) continue;
      final value = _numericValue(signal);
      final description = signal['description']?.toString() ?? '';
      if (description.isNotEmpty && value != null) {
        final code = value.round();
        for (final rawPart in description.split(';')) {
          final part = rawPart.trim();
          if (!part.contains(',')) continue;
          final idx = part.indexOf(',');
          final lhs = int.tryParse(part.substring(0, idx).trim());
          if (lhs == code) return part.substring(idx + 1).trim();
        }
      }
      final s = signal['value']?.toString();
      if (s != null && s.isNotEmpty) return s;
    }
    return null;
  }

  static String _titleCase(String text) => text
      .replaceAll('_', ' ')
      .split(' ')
      .where((e) => e.isNotEmpty)
      .map((e) => e[0].toUpperCase() + e.substring(1))
      .join(' ');
}
