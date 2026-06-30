import 'package:flutter/material.dart';

import '../models/telemetry_signal.dart';

class AssetFieldGroup {
  const AssetFieldGroup({required this.label, required this.icon, required this.terms});

  final String label;
  final IconData icon;
  final List<String> terms;

  bool matches(TelemetrySignal signal) {
    final haystack = _haystack(signal);
    return terms.any((term) => haystack.contains(term.toLowerCase()));
  }
}

class AssetUiProfile {
  const AssetUiProfile({
    required this.assetIdTerms,
    required this.title,
    required this.operatorPurpose,
    required this.icon,
    required this.primaryTerms,
    required this.groups,
    this.defaultCategory,
  });

  final List<String> assetIdTerms;
  final String title;
  final String operatorPurpose;
  final IconData icon;
  final List<String> primaryTerms;
  final List<AssetFieldGroup> groups;
  final String? defaultCategory;

  bool matchesAsset(String assetId) {
    final id = assetId.toLowerCase();
    return assetIdTerms.any((term) => id.contains(term.toLowerCase()));
  }

  List<TelemetrySignal> primarySignals(List<TelemetrySignal> signals, {int maxCount = 12}) {
    final sorted = [...signals];
    sorted.sort((a, b) => _score(a).compareTo(_score(b)));
    final primary = sorted.where((s) => _score(s) < 1000).take(maxCount).toList();
    return primary.isNotEmpty ? primary : sorted.take(maxCount).toList();
  }

  List<GroupedSignals> groupedSignals(List<TelemetrySignal> signals) {
    final groupsOut = <GroupedSignals>[];
    final usedNames = <String>{};
    for (final group in groups) {
      final items = signals.where(group.matches).toList();
      if (items.isEmpty) continue;
      items.sort(_signalSort);
      usedNames.addAll(items.map((s) => s.name));
      groupsOut.add(GroupedSignals(label: group.label, icon: group.icon, signals: items));
    }
    final remaining = signals.where((s) => !usedNames.contains(s.name)).toList()..sort(_signalSort);
    if (remaining.isNotEmpty) {
      groupsOut.add(GroupedSignals(label: 'Other Fields', icon: Icons.more_horiz, signals: remaining));
    }
    return groupsOut;
  }

  int _score(TelemetrySignal signal) {
    final haystack = _haystack(signal);
    for (var i = 0; i < primaryTerms.length; i++) {
      if (haystack.contains(primaryTerms[i].toLowerCase())) return i;
    }
    if (haystack.contains('alarm') || haystack.contains('fault')) return 900;
    return 1000;
  }
}

class GroupedSignals {
  const GroupedSignals({required this.label, required this.icon, required this.signals});

  final String label;
  final IconData icon;
  final List<TelemetrySignal> signals;
}

class AssetFieldStrategy {
  const AssetFieldStrategy._();

  static AssetUiProfile forAsset(String assetId) {
    final id = assetId.toLowerCase();
    return _profiles.firstWhere((profile) => profile.matchesAsset(id), orElse: () => genericProfile);
  }

  static IconData iconForAsset(String assetId) => forAsset(assetId).icon;

  static const genericProfile = AssetUiProfile(
    assetIdTerms: [''],
    title: 'Asset',
    operatorPurpose: 'General asset fields and decoded NorthBound telemetry.',
    icon: Icons.hub,
    primaryTerms: ['status', 'power', 'voltage', 'current', 'temperature', 'alarm', 'fault'],
    groups: [
      AssetFieldGroup(label: 'Status', icon: Icons.info_outline, terms: ['status', 'mode', 'state']),
      AssetFieldGroup(label: 'Power', icon: Icons.bolt, terms: ['power', 'kw', 'kvar', 'kva', 'factor']),
      AssetFieldGroup(label: 'Voltage', icon: Icons.electrical_services, terms: ['voltage', 'volt']),
      AssetFieldGroup(label: 'Current', icon: Icons.timeline, terms: ['current', 'amp']),
      AssetFieldGroup(label: 'Temperature', icon: Icons.thermostat, terms: ['temperature', 'temp']),
      AssetFieldGroup(label: 'Faults / Alarms', icon: Icons.warning_amber, terms: ['fault', 'alarm', 'warning', 'trip']),
    ],
  );

  static const List<AssetUiProfile> _profiles = [
    AssetUiProfile(
      assetIdTerms: ['ems_system', 'existing_ems'],
      title: 'EMS System',
      operatorPurpose: 'System-level operating mode, remote/local state, PCS/BMS readiness, site power and high-level safety state.',
      icon: Icons.account_tree,
      primaryTerms: ['soc', 'ess power', 'load power', 'remote mode', 'manual', 'auto', 'pcs status', 'bms status', 'running status', 'available charge', 'available discharge', 'system fault', 'emergency stop', 'fire'],
      groups: [
        AssetFieldGroup(label: 'Operating Modes', icon: Icons.tune, terms: ['mode', 'manual', 'auto', 'remote', 'local', 'master', 'slave']),
        AssetFieldGroup(label: 'System Status', icon: Icons.health_and_safety, terms: ['status', 'running', 'available', 'communication', 'comm']),
        AssetFieldGroup(label: 'SOC / Limits', icon: Icons.battery_5_bar, terms: ['soc', 'soh', 'cutoff', 'limit']),
        AssetFieldGroup(label: 'Power / Commands', icon: Icons.bolt, terms: ['power', 'kw', 'charge', 'discharge', 'command', 'load']),
        AssetFieldGroup(label: 'Faults / Safety', icon: Icons.warning_amber, terms: ['fault', 'alarm', 'emergency', 'fire', 'stop']),
      ],
    ),
    AssetUiProfile(
      assetIdTerms: ['bms'],
      title: 'BMS',
      operatorPurpose: 'Battery safety view: SOC/SOH, pack voltage/current, cell voltage/temperature, insulation, contactors and BMS alarms.',
      icon: Icons.battery_5_bar,
      primaryTerms: ['display soc', 'internal soc', 'soh', 'total voltage', 'rack current', 'current', 'max cell voltage', 'min cell voltage', 'max temp', 'min temp', 'insulation', 'contactor', 'precharge', 'fault', 'alarm'],
      groups: [
        AssetFieldGroup(label: 'SOC / SOH', icon: Icons.battery_5_bar, terms: ['soc', 'soh']),
        AssetFieldGroup(label: 'Pack / Cell Voltage', icon: Icons.electrical_services, terms: ['voltage', 'cell', 'volt', 'overvoltage', 'undervoltage']),
        AssetFieldGroup(label: 'Current / Power', icon: Icons.bolt, terms: ['current', 'power', 'charge current', 'discharge current']),
        AssetFieldGroup(label: 'Temperature', icon: Icons.thermostat, terms: ['temperature', 'temp', 'ntc']),
        AssetFieldGroup(label: 'Insulation', icon: Icons.shield, terms: ['insulation', 'resistance']),
        AssetFieldGroup(label: 'Contactors / Precharge', icon: Icons.power_settings_new, terms: ['contactor', 'precharge', 'relay']),
        AssetFieldGroup(label: 'Communication', icon: Icons.settings_ethernet, terms: ['communication', 'comm', 'can', 'bmu', 'bau', 'pcs']),
        AssetFieldGroup(label: 'Energy / Capacity', icon: Icons.stacked_line_chart, terms: ['energy', 'capacity', 'cumulative']),
        AssetFieldGroup(label: 'Faults / Alarms', icon: Icons.warning_amber, terms: ['fault', 'alarm', 'warning', 'protect', 'fuse']),
      ],
    ),
    AssetUiProfile(
      assetIdTerms: ['pcs'],
      title: 'PCS',
      operatorPurpose: 'Power-conversion view: active/reactive power, AC/DC electrical values, run mode, grid mode, temperatures, insulation and PCS faults.',
      icon: Icons.electrical_services,
      primaryTerms: ['pcs soc', 'dc power', 'active power', 'charge power', 'discharge power', 'available charge', 'available discharge', 'frequency', 'voltage', 'current', 'running mode', 'fault', 'heatsink', 'temperature', 'insulation'],
      groups: [
        AssetFieldGroup(label: 'Status / Mode', icon: Icons.info_outline, terms: ['status', 'mode', 'state', 'running', 'grid', 'off-grid', 'on-grid']),
        AssetFieldGroup(label: 'Power', icon: Icons.bolt, terms: ['power', 'kw', 'kvar', 'kva', 'factor', 'charge', 'discharge']),
        AssetFieldGroup(label: 'AC Side', icon: Icons.power, terms: ['ac', 'phase', 'line', 'ab', 'bc', 'ca', 'frequency', 'grid']),
        AssetFieldGroup(label: 'DC Side', icon: Icons.battery_charging_full, terms: ['dc', 'bus', 'battery', 'bms total']),
        AssetFieldGroup(label: 'Voltage', icon: Icons.electrical_services, terms: ['voltage', 'volt']),
        AssetFieldGroup(label: 'Current', icon: Icons.timeline, terms: ['current', 'amp']),
        AssetFieldGroup(label: 'Temperature', icon: Icons.thermostat, terms: ['temperature', 'temp', 'heatsink', 'igbt']),
        AssetFieldGroup(label: 'Insulation', icon: Icons.shield, terms: ['insulation', 'resistance']),
        AssetFieldGroup(label: 'Energy', icon: Icons.stacked_line_chart, terms: ['energy', 'cumulative']),
        AssetFieldGroup(label: 'Faults / Alarms', icon: Icons.warning_amber, terms: ['fault', 'alarm', 'protect', 'trip', 'error']),
      ],
    ),
    AssetUiProfile(
      assetIdTerms: ['meter'],
      title: 'Utility Meter',
      operatorPurpose: 'Grid/meter electrical measurements: voltage, current, power, energy, frequency, power factor and meter alarms.',
      icon: Icons.speed,
      primaryTerms: ['total active power', 'total reactive power', 'apparent power', 'power factor', 'frequency', 'ab line voltage', 'bc line voltage', 'ca line voltage', 'current', 'energy', 'alarm'],
      groups: [
        AssetFieldGroup(label: 'Voltage', icon: Icons.electrical_services, terms: ['voltage', 'volt', 'line']),
        AssetFieldGroup(label: 'Current', icon: Icons.timeline, terms: ['current', 'amp']),
        AssetFieldGroup(label: 'Power / PF', icon: Icons.bolt, terms: ['power', 'kw', 'kvar', 'kva', 'factor']),
        AssetFieldGroup(label: 'Energy', icon: Icons.stacked_line_chart, terms: ['energy', 'kwh']),
        AssetFieldGroup(label: 'Frequency / Temperature', icon: Icons.monitor_heart, terms: ['frequency', 'temperature', 'temp']),
        AssetFieldGroup(label: 'Alarms', icon: Icons.warning_amber, terms: ['alarm', 'fault', 'over', 'under', 'phase loss']),
      ],
    ),
    AssetUiProfile(
      assetIdTerms: ['fire'],
      title: 'Fire Protection',
      operatorPurpose: 'Safety panel for fire, smoke, CO, IR, temperature, start/feedback and fire-system faults.',
      icon: Icons.local_fire_department,
      primaryTerms: ['comm', 'temperature', 'fire alarm', 'fault', 'co', 'infrared', 'smoke', 'start', 'feedback', 'fan damper', 'audible'],
      groups: [
        AssetFieldGroup(label: 'Communication / Status', icon: Icons.settings_ethernet, terms: ['comm', 'status']),
        AssetFieldGroup(label: 'Temperature', icon: Icons.thermostat, terms: ['temperature', 'temp']),
        AssetFieldGroup(label: 'Fire / Gas / IR', icon: Icons.local_fire_department, terms: ['fire', 'co', 'infrared', 'smoke']),
        AssetFieldGroup(label: 'Outputs / Feedback', icon: Icons.output, terms: ['start', 'feedback', 'fan', 'damper', 'audible', 'visual']),
        AssetFieldGroup(label: 'Faults / Alarms', icon: Icons.warning_amber, terms: ['fault', 'alarm']),
      ],
    ),
    AssetUiProfile(
      assetIdTerms: ['cooling'],
      title: 'Liquid Cooling',
      operatorPurpose: 'Thermal-management panel: water temperatures, pressure, setpoints, compressor/pump state, power supply and cooling alarms.',
      icon: Icons.ac_unit,
      primaryTerms: ['working mode', 'start', 'inlet water temperature', 'outlet water temperature', 'temperature difference', 'cooling setpoint', 'heating setpoint', 'water pressure', 'smoke alarm', 'water ingress', 'water flow', 'compressor', 'pump', 'fault'],
      groups: [
        AssetFieldGroup(label: 'Mode / Status', icon: Icons.tune, terms: ['mode', 'status', 'start', 'stop', 'monitoring', 'control']),
        AssetFieldGroup(label: 'Temperature / Setpoints', icon: Icons.thermostat, terms: ['temperature', 'temp', 'cooling', 'heating', 'setpoint', 'target']),
        AssetFieldGroup(label: 'Pressure / Flow', icon: Icons.water, terms: ['pressure', 'flow', 'pump', 'water']),
        AssetFieldGroup(label: 'Compressor / Fan', icon: Icons.precision_manufacturing, terms: ['compressor', 'fan', 'frequency']),
        AssetFieldGroup(label: 'Power Supply', icon: Icons.power, terms: ['power supply', 'overvoltage', 'undervoltage', 'phase', 'voltage']),
        AssetFieldGroup(label: 'Communication', icon: Icons.settings_ethernet, terms: ['communication', 'comm', 'can', 'spi', 'rs485', 'network']),
        AssetFieldGroup(label: 'Faults / Alarms', icon: Icons.warning_amber, terms: ['fault', 'alarm', 'smoke', 'ingress', 'low level']),
      ],
    ),
    AssetUiProfile(
      assetIdTerms: ['dehumidifier', 'humid'],
      title: 'Dehumidifier',
      operatorPurpose: 'Environmental-control panel: temperature/humidity setpoints, current readings, dehumidification state and alarm status.',
      icon: Icons.water_drop,
      primaryTerms: ['working mode', 'temperature setpoint', 'humidity setpoint', 'current temperature', 'current humidity', 'dehumidification', 'alarm'],
      groups: [
        AssetFieldGroup(label: 'Temperature', icon: Icons.thermostat, terms: ['temperature', 'temp']),
        AssetFieldGroup(label: 'Humidity', icon: Icons.water_drop, terms: ['humidity', 'humid']),
        AssetFieldGroup(label: 'Mode / Status', icon: Icons.tune, terms: ['mode', 'status', 'dehumidification', 'control']),
        AssetFieldGroup(label: 'Alarms', icon: Icons.warning_amber, terms: ['alarm', 'fault']),
      ],
    ),
    AssetUiProfile(
      assetIdTerms: ['io'],
      title: 'I/O Module',
      operatorPurpose: 'Digital interlock panel: water ingress, PCS fault input, E-stop, breaker feedback/control, fire sprinkler, door/access and DO/DI states.',
      icon: Icons.input,
      primaryTerms: ['comm', 'water ingress', 'pcs fault', 'emergency stop', 'breaker', 'fire protection', 'sprinkler', 'running indicator', 'door', 'fault'],
      groups: [
        AssetFieldGroup(label: 'Communication / Status', icon: Icons.settings_ethernet, terms: ['comm', 'status']),
        AssetFieldGroup(label: 'Digital Inputs', icon: Icons.input, terms: ['input', 'di', 'feedback', 'signal', 'door', 'ingress']),
        AssetFieldGroup(label: 'Digital Outputs', icon: Icons.output, terms: ['output', 'do', 'control', 'indicator', 'sprinkler']),
        AssetFieldGroup(label: 'Safety / Faults', icon: Icons.warning_amber, terms: ['fault', 'alarm', 'emergency', 'stop', 'pcs fault']),
      ],
    ),
    AssetUiProfile(
      assetIdTerms: ['remote'],
      title: 'Remote Status',
      operatorPurpose: 'Read-only remote schedule/status view: SOC limits, remote mode and time-of-use power schedule periods.',
      icon: Icons.schedule,
      primaryTerms: ['remote mode', 'control mode', 'soc limit', 'charge cutoff', 'discharge cutoff', 'period 1', 'period 2', 'active power', 'start time', 'end time', 'fault reset'],
      groups: [
        AssetFieldGroup(label: 'Remote Mode / Limits', icon: Icons.tune, terms: ['remote', 'mode', 'soc', 'limit', 'cutoff']),
        AssetFieldGroup(label: 'Schedule Power', icon: Icons.bolt, terms: ['period', 'active power', 'power']),
        AssetFieldGroup(label: 'Schedule Time', icon: Icons.schedule, terms: ['start time', 'end time', 'hour', 'minute', 'time']),
        AssetFieldGroup(label: 'Status / Fault Reset', icon: Icons.restart_alt, terms: ['status', 'fault reset', 'reset']),
      ],
    ),
  ];
}

String _haystack(TelemetrySignal signal) {
  return '${signal.name} ${signal.displayName} ${signal.category} ${signal.description ?? ''} ${signal.unit ?? ''}'.toLowerCase();
}

int _signalSort(TelemetrySignal a, TelemetrySignal b) {
  final c = a.category.compareTo(b.category);
  if (c != 0) return c;
  final aa = a.address ?? 99999999;
  final bb = b.address ?? 99999999;
  if (aa != bb) return aa.compareTo(bb);
  return a.displayName.compareTo(b.displayName);
}
