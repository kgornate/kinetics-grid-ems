import '../models/pcs_fault_item.dart';
import '../models/pcs_source_snapshot.dart';
import '../models/source_summary.dart';

class PcsPageBuilder {
  const PcsPageBuilder._();

  static PcsSourceSnapshot buildForSource({
    required SourceSummary source,
    Map<String, dynamic>? pcsTelemetry,
    Map<String, dynamic>? emsTelemetry,
    bool fallbackOnline = false,
  }) {
    final pcsSignals = _flattenSignals(pcsTelemetry);
    final emsSignals = _flattenSignals(emsTelemetry);
    final merged = <String, Map<String, dynamic>>{...pcsSignals, ...emsSignals};

    final activePower = _valueOf(merged, const [
      'total_active_power',
      'active_power',
      'energy_storage_power',
      'ess_power',
    ]);

    final dcPower = _valueOf(merged, const [
      'dc_power_2',
      'dc_power',
      'dc_side_power',
      'battery_side_power',
    ]);

    final gridFrequency = _valueOf(merged, const [
      'grid_frequency',
      'ac_frequency',
      'frequency',
      'grid_frequency_hz',
    ]);

    final acVoltage = _averageOf(merged, const [
          'phase_a_voltage',
          'phase_b_voltage',
          'phase_c_voltage',
        ]) ??
        _valueOf(merged, const [
          'output_voltage',
          'line_voltage',
          'phase_ab_voltage',
          'phase_ac_voltage',
          'phase_bc_voltage',
        ]);

    final acCurrent = _averageOf(merged, const [
          'phase_a_current',
          'phase_b_current',
          'phase_c_current',
          'phase_a_current_rms',
          'phase_b_current_rms',
          'phase_c_current_rms',
        ]) ??
        _valueOf(merged, const [
          'output_current',
          'line_current',
          'phase_n_current_rms',
          'dc_current',
        ]);

    final dcVoltage = _valueOf(merged, const [
          'dc_voltage',
          'battery_dc_voltage',
        ]) ??
        _averageOf(merged, const [
          'pcs_capacitor_upper_dc_voltage',
          'pcs_capacitor_lower_dc_voltage',
          'upper_dc_link_voltage',
          'lower_dc_link_voltage',
        ]);

    final runningStatus = _enumLabelOf(merged, const [
          'pcs_running_status',
          'running_status',
          'pcs_status',
        ]) ??
        _runningIndicatorLabel(_valueOf(merged, const ['running_indicator'])) ??
        ((pcsTelemetry?['online'] == true || emsTelemetry?['online'] == true || fallbackOnline)
            ? 'Online'
            : 'Offline');

    final explicitChargeState = _enumLabelOf(merged, const [
      'status',
      'charge_discharge_status',
      'charge_or_discharge_status',
    ]);
    final chargeDischarge = _resolveChargeDischarge(
      explicitChargeState,
      activePower,
    );

    final operatingMode = _enumLabelOf(merged, const [
          'operation_mode',
          'working_mode',
          'unit_operation_mode',
          'monitor_mode',
        ]) ??
        _enumLabelOf(merged, const ['pcs_running_status']) ??
        chargeDischarge;

    final gridMode = _enumLabelOf(merged, const [
          'pcs_on_off_grid_status',
          'pcs_grid_on_off_status',
          'on_off_grid_switching',
          'manual_on_off_grid_switching',
          'grid_mode',
          'on_off_grid_setting',
        ]) ??
        'Unavailable';

    final faultItems = _collectFaultLikeItems(merged, wantAlarm: false);
    final alarmItems = _collectFaultLikeItems(merged, wantAlarm: true);

    final faultSummary = faultItems.any((e) => e.active)
        ? '${faultItems.where((e) => e.active).length} active'
        : (faultItems.isEmpty ? 'Unavailable' : 'Normal');
    final alarmSummary = alarmItems.any((e) => e.active)
        ? '${alarmItems.where((e) => e.active).length} active'
        : (alarmItems.isEmpty ? 'Unavailable' : 'Normal');

    return PcsSourceSnapshot(
      sourceId: source.sourceId,
      displayName: source.displayName,
      host: source.host,
      port: source.port,
      online: (pcsTelemetry?['online'] == true) ||
          (emsTelemetry?['online'] == true) ||
          fallbackOnline,
      runningStatusLabel: runningStatus,
      operatingModeLabel: operatingMode,
      gridModeLabel: gridMode,
      chargeDischargeLabel: chargeDischarge,
      faultSummaryLabel: faultSummary,
      alarmSummaryLabel: alarmSummary,
      faultItems: faultItems,
      alarmItems: alarmItems,
      activePowerKw: activePower,
      dcPowerKw: dcPower,
      gridFrequencyHz: gridFrequency,
      acVoltageV: acVoltage,
      acCurrentA: acCurrent,
      dcVoltageV: dcVoltage,
    );
  }

  static Map<String, Map<String, dynamic>> _flattenSignals(Map<String, dynamic>? telemetry) {
    final out = <String, Map<String, dynamic>>{};
    if (telemetry == null) return out;

    void addFrom(dynamic section) {
      final map = (section as Map?)?.cast<String, dynamic>() ?? {};
      for (final entry in map.entries) {
        final value = (entry.value as Map?)?.cast<String, dynamic>() ?? {};
        out[entry.key] = value;
      }
    }

    addFrom(telemetry['signals']);
    addFrom(telemetry['key_signals']);
    return out;
  }

  static List<PcsFaultItem> _collectFaultLikeItems(
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
      final desc = signal['description']?.toString() ?? '';
      final mapped = _mapEnumDescription(desc, value) ?? signal['value']?.toString() ?? '--';
      final normalized = mapped.toLowerCase();
      final active = _isActiveState(value, normalized);
      final displayName = signal['display_name']?.toString() ?? _titleCase(entry.key);
      items.add(PcsFaultItem(
        signalName: entry.key,
        displayName: displayName,
        category: wantAlarm ? 'alarm' : 'fault',
        stateLabel: mapped,
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

  static bool _isActiveState(double? value, String normalizedLabel) {
    const inactiveWords = ['normal', 'no fault', 'no alarm', 'open', 'closed', 'stopped', 'standby', 'offline'];
    if (inactiveWords.contains(normalizedLabel)) return false;
    if (normalizedLabel.contains('invalid')) return false;
    if (value != null) {
      if (value == 0) return false;
      return true;
    }
    return normalizedLabel.isNotEmpty && normalizedLabel != '--';
  }

  static String _titleCase(String text) => text
      .replaceAll('_', ' ')
      .split(' ')
      .where((e) => e.isNotEmpty)
      .map((e) => e[0].toUpperCase() + e.substring(1))
      .join(' ');

  static double? _valueOf(Map<String, Map<String, dynamic>> signals, List<String> names) {
    for (final name in names) {
      if (!signals.containsKey(name)) continue;
      final value = _numericValue(signals[name]);
      if (value != null) return value;
    }
    return null;
  }

  static double? _averageOf(Map<String, Map<String, dynamic>> signals, List<String> names) {
    final values = <double>[];
    for (final name in names) {
      final value = _valueOf(signals, [name]);
      if (value != null) values.add(value);
    }
    if (values.isEmpty) return null;
    return values.reduce((a, b) => a + b) / values.length;
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
      final label = _mapEnumDescription(description, value);
      if (label != null) return label;
      final stringValue = signal['value']?.toString();
      if (stringValue != null && stringValue.isNotEmpty) return stringValue;
    }
    return null;
  }

  static String? _mapEnumDescription(String description, double? value) {
    if (description.isEmpty || value == null) return null;
    final code = value.round();
    final parts = description.split(';');
    for (final rawPart in parts) {
      final part = rawPart.trim();
      if (part.isEmpty || !part.contains(',')) continue;
      final idx = part.indexOf(',');
      final lhs = part.substring(0, idx).trim();
      final rhs = part.substring(idx + 1).trim();
      final lhsNum = int.tryParse(lhs);
      if (lhsNum != null && lhsNum == code) return rhs;
    }
    return null;
  }

  static String _resolveChargeDischarge(String? explicitLabel, double? activePower) {
    final powerDerived = _deriveChargeDischargeFromPower(activePower);
    if (explicitLabel == null || explicitLabel.trim().isEmpty) return powerDerived;

    final normalized = explicitLabel.toLowerCase().trim();
    if (normalized.contains('discharge')) return 'Discharging';
    if (normalized.contains('charge')) return 'Charging';
    if (normalized.contains('standby') || normalized.contains('idle') || normalized.contains('stop')) {
      return powerDerived == 'Standby' ? 'Standby' : powerDerived;
    }
    return explicitLabel;
  }

  static String _deriveChargeDischargeFromPower(double? activePower) {
    if (activePower == null) return 'Unavailable';
    if (activePower > 0.3) return 'Discharging';
    if (activePower < -0.3) return 'Charging';
    return 'Standby';
  }

  static String? _runningIndicatorLabel(double? value) {
    if (value == null) return null;
    return value.round() == 1 ? 'Running' : 'Stopped';
  }
}
