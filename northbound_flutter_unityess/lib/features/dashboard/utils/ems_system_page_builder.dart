
import '../models/ems_system_source_snapshot.dart';
import '../models/pcs_fault_item.dart';
import '../models/source_summary.dart';

class EmsSystemPageBuilder {
  const EmsSystemPageBuilder._();

  static EmsSystemSourceSnapshot buildForSource({
    required SourceSummary source,
    Map<String, dynamic>? emsTelemetry,
    bool fallbackOnline = false,
  }) {
    final signals = _flattenSignals(emsTelemetry);

    final systemStatus = _enumLabelOf(signals, const [
          'status',
          'system_status',
          'running_status',
          'operating_status',
        ]) ??
        (((emsTelemetry?['online'] == true) || fallbackOnline) ? 'Online' : 'Offline');

    final manualAuto = _enumLabelOf(signals, const [
          'manual_auto_mode',
        ]) ??
        'Unavailable';

    final manualModeControl = _enumLabelOf(signals, const [
          'manual_mode_control',
        ]) ??
        'Unavailable';

    final autoModeControl = _enumLabelOf(signals, const [
          'auto_mode_control',
        ]) ??
        'Unavailable';

    final chargeDischargeControl = _enumLabelOf(signals, const [
          'charge_discharge_control_mode',
        ]) ??
        'Unavailable';

    final powerCommand = _enumLabelOf(signals, const [
          'power_on_command',
        ]) ??
        'Unavailable';

    final pcsPowerControl = _enumLabelOf(signals, const [
          'pcs_power_on_off_control',
        ]) ??
        'Unavailable';

    final bmsPowerControl = _enumLabelOf(signals, const [
          'bms_power_on_off_control',
        ]) ??
        'Unavailable';

    final faultItems = _collectStateItems(signals, wantAlarm: false);
    final alarmItems = _collectStateItems(signals, wantAlarm: true);
    final configItems = _collectConfigItems(signals);

    final activeFaults = faultItems.where((e) => e.active).length;
    final activeAlarms = alarmItems.where((e) => e.active).length;

    return EmsSystemSourceSnapshot(
      sourceId: source.sourceId,
      displayName: source.displayName,
      host: source.host,
      port: source.port,
      online: (emsTelemetry?['online'] == true) || fallbackOnline,
      systemStatusLabel: _professionalStateLabel(systemStatus),
      manualAutoModeLabel: _professionalStateLabel(manualAuto),
      manualModeControlLabel: _professionalStateLabel(manualModeControl),
      autoModeControlLabel: _professionalStateLabel(autoModeControl),
      chargeDischargeControlModeLabel: _professionalStateLabel(chargeDischargeControl),
      powerCommandLabel: _professionalStateLabel(powerCommand),
      pcsPowerControlLabel: _professionalStateLabel(pcsPowerControl),
      bmsPowerControlLabel: _professionalStateLabel(bmsPowerControl),
      faultSummaryLabel: activeFaults > 0 ? '$activeFaults active' : (faultItems.isEmpty ? 'Normal' : 'Normal'),
      alarmSummaryLabel: activeAlarms > 0 ? '$activeAlarms active' : (alarmItems.isEmpty ? 'Normal' : 'Normal'),
      faultItems: faultItems,
      alarmItems: alarmItems,
      configItems: configItems,
      chargeCutoffSocPct: _valueOf(signals, const [
        'battery_charge_cutoff_soc_setting',
        'charge_cutoff_soc_setting',
        'charge_cutoff_soc',
      ]),
      dischargeCutoffSocPct: _valueOf(signals, const [
        'battery_discharge_cutoff_soc_setting',
        'discharge_cutoff_soc_setting',
        'discharge_cutoff_soc',
      ]),
      chargeLimitKw: _valueOf(signals, const [
        'battery_charge_limit_kw_setting',
        'charge_limit_kw_setting',
        'charge_limit_kw',
      ]),
      dischargeLimitKw: _valueOf(signals, const [
        'battery_discharge_limit_kw_setting',
        'discharge_limit_kw_setting',
        'discharge_limit_kw',
      ]),
      actualActivePowerKw: _valueOf(signals, const [
        'total_active_power',
        'active_power',
        'grid_current_total_power',
      ]),
      batterySocPct: _valueOf(signals, const [
        'cluster_internal_soc',
        'soc',
        'battery_soc',
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
          key.contains('recovery') ||
          key.contains('control'))) {
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
      if (names.any((n) => key.contains(n.toLowerCase()))) return entry.value;
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
    if (enumLabel != null && enumLabel.trim().isNotEmpty) return _professionalStateLabel(enumLabel);
    final displayValue = signal['display_value']?.toString();
    if (displayValue != null && displayValue.trim().isNotEmpty) return displayValue;
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
