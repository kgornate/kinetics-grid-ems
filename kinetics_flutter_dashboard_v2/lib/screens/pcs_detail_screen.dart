import 'package:flutter/material.dart';

import '../core/presentation/telemetry_presentation.dart';
import '../core/state/gateway_controller.dart';
import '../models/gateway_models.dart';
import '../widgets/common_widgets.dart';

class PcsDetailScreen extends StatelessWidget {
  const PcsDetailScreen({
    super.key,
    required this.controller,
    required this.assetId,
  });

  final GatewayController controller;
  final String assetId;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final asset = controller.plant.assets[assetId];
        if (asset == null) {
          return const Scaffold(
            body: Center(child: Text('PCS asset is not available.')),
          );
        }
        final title = asset.label?.trim().isNotEmpty == true
            ? asset.label!
            : 'PCS ${asset.unitId ?? asset.assetId}';
        return DefaultTabController(
          length: 8,
          child: Scaffold(
            appBar: AppBar(
              title: Text('$title / Modbus RTU ID ${asset.unitId ?? '--'}'),
              actions: [
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  child: StatusPill(
                    label: asset.online ? 'Online' : 'Offline',
                    good: asset.online,
                  ),
                ),
                const SizedBox(width: 8),
                IconButton(
                  tooltip: 'Refresh PCS telemetry',
                  onPressed: controller.busy
                      ? null
                      : () => controller.refreshCompact(),
                  icon: const Icon(Icons.refresh),
                ),
                const SizedBox(width: 8),
              ],
              bottom: const TabBar(
                isScrollable: true,
                tabs: [
                  Tab(text: 'Overview'),
                  Tab(text: 'DC side'),
                  Tab(text: 'AC / Grid'),
                  Tab(text: 'Thermal'),
                  Tab(text: 'Operating status'),
                  Tab(text: 'Alarms & faults'),
                  Tab(text: 'Settings'),
                  Tab(text: 'All signals'),
                ],
              ),
            ),
            body: asset.telemetry.isEmpty
                ? _OfflineBody(asset: asset)
                : TabBarView(
                    children: [
                      _overview(context, asset),
                      _sectionPage(
                        asset,
                        'DC-side electrical measurements',
                        entriesForKeys(asset, const [
                          'dc_bus_voltage',
                          'dc_bus_current',
                          'battery_voltage',
                          'battery_current',
                          'dc_power',
                          'positive_bus_voltage',
                          'negative_bus_voltage',
                          'auxiliary_bus_voltage',
                          'battery_positive_ground_impedance',
                          'battery_negative_ground_impedance',
                        ]),
                      ),
                      _sectionPage(
                        asset,
                        'AC, grid and PCC measurements',
                        entriesForKeys(asset, const [
                          'grid_ab_voltage',
                          'grid_bc_voltage',
                          'grid_ca_voltage',
                          'grid_a_current',
                          'grid_b_current',
                          'grid_c_current',
                          'grid_n_current',
                          'grid_frequency',
                          'grid_active_power',
                          'grid_reactive_power',
                          'grid_apparent_power',
                          'power_factor',
                          'inverter_ab_voltage',
                          'inverter_bc_voltage',
                          'inverter_ca_voltage',
                          'pcc_ab_voltage',
                          'reg_112c',
                          'reg_112d',
                          'phase_a_to_ground_voltage',
                          'phase_b_to_ground_voltage',
                          'phase_c_to_ground_voltage',
                          'pcc_phase_compensation',
                        ]),
                      ),
                      _sectionPage(
                        asset,
                        'PCS thermal measurements',
                        entriesWhere(asset, (key, point) {
                          final lower = '${key}_${point.nameEn ?? ''}'.toLowerCase();
                          return lower.contains('temperature') ||
                              lower.contains('temp') ||
                              (point.unit ?? '').contains('℃') ||
                              (point.unit ?? '').contains('â');
                        }),
                      ),
                      _statusPage(asset),
                      _alarmsPage(context, asset),
                      _settingsPage(asset),
                      _allSignalsPage(asset),
                    ],
                  ),
          ),
        );
      },
    );
  }

  Widget _overview(BuildContext context, AssetSnapshot asset) {
    final alarms = _assetAlarms(asset.assetId);
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        SectionHeader(
          asset.label ?? 'PCS ${asset.unitId ?? ''}',
          subtitle:
              'Modbus RTU slave ID ${asset.unitId ?? '--'} • ${asset.telemetry.length} mapped points • ${asset.timestamp == null ? 'No timestamp' : shortTime(asset.timestamp!)}',
          trailing: Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              StatusPill(
                label: pcsControlLocation(asset),
                good: pcsControlLocation(asset) == 'Remote',
                icon: Icons.settings_remote,
              ),
              StatusPill(
                label: pcsAuthorizationState(asset),
                good: pcsAuthorizationState(asset) == 'Authorized',
                icon: Icons.verified_user,
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        MetricGrid(
          children: [
            _metric(asset, 'operating_state', 'Operating state', Icons.power_settings_new, emphasis: true),
            _metric(asset, 'actual_product_mode', 'Product mode', Icons.hub, emphasis: true),
            _metric(asset, 'actual_pq_mode', 'PQ mode', Icons.tune),
            _metric(asset, 'dc_bus_voltage', 'DC bus voltage', Icons.battery_charging_full, emphasis: true),
            _metric(asset, 'dc_bus_current', 'DC bus current', Icons.electric_meter),
            _metric(asset, 'grid_active_power', 'Active power', Icons.power, emphasis: true),
            _metric(asset, 'grid_reactive_power', 'Reactive power', Icons.swap_horiz),
            _metric(asset, 'grid_frequency', 'Grid frequency', Icons.show_chart),
            _metric(asset, 'power_factor', 'Power factor', Icons.speed),
            MetricTile(
              label: 'Average grid voltage',
              value: _averageGridVoltage(asset),
              icon: Icons.bolt,
              emphasis: true,
            ),
            MetricTile(
              label: 'Highest PCS temperature',
              value: _highestTemperature(asset),
              icon: Icons.thermostat,
            ),
            MetricTile(
              label: 'Active alarms',
              value: '${alarms.length}',
              subtitle: '${pcsActiveFaultBitCount(asset)} active decoded fault/status bits',
              icon: Icons.warning_amber,
            ),
          ],
        ),
        const SizedBox(height: 20),
        TelemetrySection(
          title: 'Key DC measurements',
          asset: asset,
          entries: entriesForKeys(asset, const [
            'dc_bus_voltage',
            'dc_bus_current',
            'battery_voltage',
            'battery_current',
            'dc_power',
            'positive_bus_voltage',
            'negative_bus_voltage',
          ]),
        ),
        TelemetrySection(
          title: 'Key AC and grid measurements',
          asset: asset,
          entries: entriesForKeys(asset, const [
            'grid_ab_voltage',
            'grid_bc_voltage',
            'grid_ca_voltage',
            'grid_a_current',
            'grid_b_current',
            'grid_c_current',
            'grid_frequency',
            'grid_active_power',
            'grid_reactive_power',
            'grid_apparent_power',
            'power_factor',
          ]),
        ),
        TelemetrySection(
          title: 'Key temperatures',
          asset: asset,
          entries: entriesForKeys(asset, const [
            'igbt_a_temperature',
            'igbt_b_temperature',
            'igbt_c_temperature',
            'cabinet_temperature',
          ]),
        ),
        if (alarms.isNotEmpty) ...[
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Active gateway alarms',
                    style: Theme.of(context)
                        .textTheme
                        .titleMedium
                        ?.copyWith(fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 8),
                  ...alarms.take(6).map(_alarmTile),
                ],
              ),
            ),
          ),
        ],
        const SizedBox(height: 40),
      ],
    );
  }

  Widget _statusPage(AssetSnapshot asset) {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        SectionHeader(
          'Operating status',
          subtitle: 'Run state, mode, authorization, breaker and safety feedback',
        ),
        const SizedBox(height: 16),
        MetricGrid(
          children: [
            _metric(asset, 'operating_state', 'Operating state', Icons.power_settings_new, emphasis: true),
            _metric(asset, 'actual_product_mode', 'Product mode', Icons.hub),
            _metric(asset, 'actual_pq_mode', 'PQ mode', Icons.tune),
            MetricTile(label: 'Control location', value: pcsControlLocation(asset), icon: Icons.settings_remote),
            MetricTile(label: 'Authorization', value: pcsAuthorizationState(asset), icon: Icons.verified_user),
            MetricTile(label: 'DC breaker', value: pcsDcBreakerState(asset), icon: Icons.electrical_services),
          ],
        ),
        const SizedBox(height: 18),
        TelemetrySection(
          title: 'Primary status words',
          asset: asset,
          entries: entriesForKeys(asset, const [
            'operating_state',
            'status_word_1',
            'status_word_2',
            'status_word_3',
            'actual_product_mode',
            'actual_pq_mode',
          ]),
        ),
        TelemetrySection(
          title: 'Additional status registers',
          asset: asset,
          entries: entriesWhere(asset, (key, point) {
            if (const {
              'operating_state',
              'status_word_1',
              'status_word_2',
              'status_word_3',
              'actual_product_mode',
              'actual_pq_mode',
            }.contains(key)) {
              return false;
            }
            return (point.category ?? '').toLowerCase() == 'status' &&
                !RegExp(r'^reg_121[0-9a]$').hasMatch(key.toLowerCase());
          }),
        ),
        const SizedBox(height: 40),
      ],
    );
  }

  Widget _alarmsPage(BuildContext context, AssetSnapshot asset) {
    final alarms = _assetAlarms(asset.assetId);
    final words = entriesWhere(
      asset,
      (key, point) => RegExp(r'^reg_121[0-9a]$').hasMatch(key.toLowerCase()),
    );
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        SectionHeader(
          'Alarms and fault words',
          subtitle:
              '${alarms.length} active gateway alarms • ${pcsActiveFaultBitCount(asset)} active decoded bits',
        ),
        const SizedBox(height: 14),
        if (alarms.isEmpty)
          const Card(
            child: ListTile(
              leading: Icon(Icons.check_circle),
              title: Text('No active gateway alarms for this PCS'),
            ),
          )
        else
          ...alarms.map((alarm) => Card(child: _alarmTile(alarm))),
        const SizedBox(height: 16),
        ...words.map((entry) => _faultWordCard(context, asset, entry)),
        const SizedBox(height: 40),
      ],
    );
  }

  Widget _settingsPage(AssetSnapshot asset) {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        SectionHeader(
          'Read-only settings and setpoints',
          subtitle: 'Values are displayed for commissioning; no write controls are exposed in Flutter.',
        ),
        const SizedBox(height: 14),
        TelemetrySection(
          title: 'Core operating settings',
          asset: asset,
          entries: entriesForKeys(asset, const [
            'reg_1400',
            'reg_1401',
            'reg_1402',
            'reg_1403',
            'reg_1404',
            'reg_1405',
            'reg_1406',
            'reg_1407',
            'reg_1408',
            'reg_1409',
            'reg_140a',
            'reg_140b',
            'reg_140c',
            'reg_140d',
            'reg_140e',
            'reg_140f',
          ]),
        ),
        TelemetrySection(
          title: 'Remaining parameters',
          asset: asset,
          entries: entriesWhere(asset, (key, point) {
            final category = (point.category ?? '').toLowerCase();
            return category == 'parameter' && !key.startsWith('reg_140');
          }),
          initiallyExpanded: false,
        ),
        TelemetrySection(
          title: 'Software and protocol versions',
          asset: asset,
          entries: entriesWhere(
            asset,
            (key, point) => (point.category ?? '').toLowerCase() == 'version',
          ),
          initiallyExpanded: false,
        ),
        const SizedBox(height: 40),
      ],
    );
  }

  Widget _allSignalsPage(AssetSnapshot asset) {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        SectionHeader(
          'All PCS signals',
          subtitle: 'Search every decoded register returned for Modbus RTU ID ${asset.unitId ?? '--'}',
        ),
        const SizedBox(height: 14),
        EngineeringTable(asset: asset),
        const SizedBox(height: 40),
      ],
    );
  }

  Widget _sectionPage(
    AssetSnapshot asset,
    String title,
    List<MapEntry<String, TelemetryPoint>> entries,
  ) {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        SectionHeader(title, subtitle: '${entries.length} mapped signals'),
        const SizedBox(height: 14),
        EngineeringTable(asset: asset, entries: entries),
        const SizedBox(height: 40),
      ],
    );
  }

  Widget _metric(
    AssetSnapshot asset,
    String key,
    String label,
    IconData icon, {
    bool emphasis = false,
  }) {
    final point = asset.telemetry[key];
    final shown = point == null
        ? const PresentedValue(value: '--', unit: '', valid: false)
        : presentPoint('pcs', key, point);
    return MetricTile(
      label: label,
      value: shown.text,
      subtitle: shown.note,
      icon: icon,
      emphasis: emphasis,
    );
  }

  String _averageGridVoltage(AssetSnapshot asset) {
    final values = const [
      'grid_ab_voltage',
      'grid_bc_voltage',
      'grid_ca_voltage',
    ]
        .map((key) => asset.telemetry[key]?.value)
        .whereType<num>()
        .map((value) => value.toDouble())
        .toList();
    if (values.isEmpty) return '--';
    final average = values.reduce((a, b) => a + b) / values.length;
    return '${average.toStringAsFixed(1)} V';
  }

  String _highestTemperature(AssetSnapshot asset) {
    final values = asset.telemetry.entries
        .where((entry) {
          final unit = normaliseUnit(entry.value.unit);
          final lower = '${entry.key}_${entry.value.nameEn ?? ''}'.toLowerCase();
          return unit == '°C' &&
              (lower.contains('temp') || lower.contains('temperature'));
        })
        .map((entry) => entry.value.value)
        .whereType<num>()
        .map((value) => value.toDouble())
        .toList();
    if (values.isEmpty) return '--';
    values.sort();
    return '${values.last.toStringAsFixed(1)} °C';
  }

  List<Map<String, dynamic>> _assetAlarms(String id) {
    return controller.activeAlarms
        .where((alarm) => alarm['asset_id']?.toString() == id)
        .toList();
  }

  Widget _alarmTile(Map<String, dynamic> alarm) {
    final title = (alarm['message'] ??
            alarm['alarm_key'] ??
            alarm['code'] ??
            'PCS alarm')
        .toString();
    final severity = (alarm['severity'] ?? 'alarm').toString();
    return ListTile(
      dense: true,
      leading: const Icon(Icons.warning_amber),
      title: Text(title),
      subtitle: Text('$severity • ${alarm['alarm_key'] ?? alarm['code'] ?? '--'}'),
    );
  }

  Widget _faultWordCard(
    BuildContext context,
    AssetSnapshot asset,
    MapEntry<String, TelemetryPoint> entry,
  ) {
    final active = activeBits(entry.value);
    final shown = presentPoint(asset.assetType, entry.key, entry.value);
    return Card(
      child: ExpansionTile(
        initiallyExpanded: active.isNotEmpty,
        leading: Icon(
          active.isEmpty ? Icons.check_circle : Icons.warning_amber,
          color: active.isEmpty
              ? Theme.of(context).colorScheme.primary
              : Theme.of(context).colorScheme.error,
        ),
        title: Text(
          friendlyName(entry.key, entry.value),
          style: const TextStyle(fontWeight: FontWeight.w800),
        ),
        subtitle: Text('${shown.text} • ${active.length} active bits'),
        children: active.isEmpty
            ? const [
                ListTile(
                  dense: true,
                  title: Text('No active decoded bits'),
                ),
              ]
            : active.map((bit) {
                final label = entry.value.bitfieldLabels[bit.key];
                return ListTile(
                  dense: true,
                  leading: const Icon(Icons.error_outline),
                  title: Text(_cleanFaultLabel(label, bit.key)),
                  subtitle: Text(bit.key),
                );
              }).toList(),
      ),
    );
  }

  String _cleanFaultLabel(String? label, String fallback) {
    if (label == null || label.trim().isEmpty) return prettifyKey(fallback);
    // The current backend may contain mojibake Chinese strings. Prefer a stable
    // English bit identifier rather than displaying unreadable text.
    if (label.contains('æ') || label.contains('å') || label.contains('ç')) {
      return prettifyKey(fallback);
    }
    return label.trim();
  }
}

class _OfflineBody extends StatelessWidget {
  const _OfflineBody({required this.asset});

  final AssetSnapshot asset;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 560),
        child: Card(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  asset.disabled ? Icons.power_off : Icons.link_off,
                  size: 54,
                  color: Theme.of(context).colorScheme.error,
                ),
                const SizedBox(height: 12),
                Text(
                  asset.disabled ? 'PCS is disabled' : 'No RTU response received',
                  style: Theme.of(context)
                      .textTheme
                      .headlineSmall
                      ?.copyWith(fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 8),
                Text(
                  'Modbus RTU slave ID ${asset.unitId ?? '--'} is configured, but it has not supplied telemetry yet. Check its RS485 wiring, power, baud rate, parity and slave ID.',
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
