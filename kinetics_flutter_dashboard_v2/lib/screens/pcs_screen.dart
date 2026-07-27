import 'package:flutter/material.dart';

import '../core/presentation/telemetry_presentation.dart';
import '../core/state/gateway_controller.dart';
import '../models/gateway_models.dart';
import '../widgets/common_widgets.dart';
import 'pcs_detail_screen.dart';

class PcsScreen extends StatelessWidget {
  const PcsScreen({super.key, required this.controller});

  final GatewayController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final devices = controller.plant.pcsDevices;
        if (devices.isEmpty) {
          return const Center(
            child: Text('No PCS devices have been published by the gateway yet.'),
          );
        }
        final online = devices.where((device) => device.online).toList();
        return RefreshIndicator(
          onRefresh: controller.refreshCompact,
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              SectionHeader(
                'PCS system',
                subtitle:
                    'Four Modbus RTU devices on the shared RS485 bus • slave IDs ${devices.map((e) => e.unitId ?? '--').join(', ')}',
                trailing: FilledButton.tonalIcon(
                  onPressed: controller.busy
                      ? null
                      : () => controller.refreshCompact(),
                  icon: const Icon(Icons.refresh),
                  label: const Text('Refresh all PCS devices'),
                ),
              ),
              const SizedBox(height: 16),
              MetricGrid(
                children: [
                  MetricTile(
                    label: 'PCS devices online',
                    value: '${online.length}/${devices.length}',
                    icon: Icons.hub,
                    emphasis: true,
                  ),
                  MetricTile(
                    label: 'Total active power',
                    value: _sum(devices, 'grid_active_power', 'kW'),
                    icon: Icons.power,
                    emphasis: true,
                  ),
                  MetricTile(
                    label: 'Total reactive power',
                    value: _sum(devices, 'grid_reactive_power', 'kvar'),
                    icon: Icons.swap_horiz,
                  ),
                  MetricTile(
                    label: 'Average grid voltage',
                    value: _averageGridVoltage(online),
                    icon: Icons.bolt,
                  ),
                  MetricTile(
                    label: 'Grid frequency',
                    value: _average(online, 'grid_frequency', 'Hz'),
                    icon: Icons.show_chart,
                  ),
                  MetricTile(
                    label: 'Highest PCS temperature',
                    value: _highestTemperature(online),
                    icon: Icons.thermostat,
                  ),
                  MetricTile(
                    label: 'Active PCS alarms',
                    value: '${_pcsAlarmCount(devices)}',
                    icon: Icons.warning_amber,
                  ),
                  MetricTile(
                    label: 'RS485 topology',
                    value: 'IDs 1–4',
                    subtitle: 'Independent PCS units on one Modbus RTU bus',
                    icon: Icons.cable,
                  ),
                ],
              ),
              const SizedBox(height: 24),
              SectionHeader(
                'PCS 1–4',
                subtitle: 'Open a PCS to view DC, grid, thermal, status, fault and setting categories.',
              ),
              const SizedBox(height: 12),
              LayoutBuilder(
                builder: (context, constraints) {
                  final columns = constraints.maxWidth > 1120
                      ? 2
                      : constraints.maxWidth > 650
                          ? 2
                          : 1;
                  return GridView.builder(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                      crossAxisCount: columns,
                      crossAxisSpacing: 12,
                      mainAxisSpacing: 12,
                      childAspectRatio: 2.05,
                    ),
                    itemCount: devices.length,
                    itemBuilder: (context, index) {
                      final device = devices[index];
                      return RichAssetCard(
                        asset: device,
                        title: device.label ?? 'PCS ${device.unitId ?? index + 1}',
                        metrics: [
                          'RTU ID ${device.unitId ?? '--'}',
                          ...pcsSummary(device),
                        ],
                        warningCount: _alarmCount(device.assetId),
                        onTap: () => Navigator.of(context).push(
                          MaterialPageRoute<void>(
                            builder: (_) => PcsDetailScreen(
                              controller: controller,
                              assetId: device.assetId,
                            ),
                          ),
                        ),
                      );
                    },
                  );
                },
              ),
              const SizedBox(height: 40),
            ],
          ),
        );
      },
    );
  }

  int _alarmCount(String id) {
    return controller.activeAlarms
        .where((alarm) => alarm['asset_id']?.toString() == id)
        .length;
  }

  int _pcsAlarmCount(List<AssetSnapshot> devices) {
    final ids = devices.map((e) => e.assetId).toSet();
    return controller.activeAlarms
        .where((alarm) => ids.contains(alarm['asset_id']?.toString()))
        .length;
  }

  String _sum(List<AssetSnapshot> devices, String key, String unit) {
    final values = devices
        .where((device) => device.online)
        .map((device) => device.telemetry[key]?.value)
        .whereType<num>()
        .map((value) => value.toDouble())
        .toList();
    if (values.isEmpty) return '--';
    final total = values.fold<double>(0, (sum, value) => sum + value);
    return '${total.toStringAsFixed(1)} $unit';
  }

  String _average(List<AssetSnapshot> devices, String key, String unit) {
    final values = devices
        .map((device) => device.telemetry[key]?.value)
        .whereType<num>()
        .map((value) => value.toDouble())
        .toList();
    if (values.isEmpty) return '--';
    final average = values.fold<double>(0, (sum, value) => sum + value) /
        values.length;
    return '${average.toStringAsFixed(2)} $unit';
  }

  String _averageGridVoltage(List<AssetSnapshot> devices) {
    final values = <double>[];
    for (final device in devices) {
      for (final key in const [
        'grid_ab_voltage',
        'grid_bc_voltage',
        'grid_ca_voltage',
      ]) {
        final value = device.telemetry[key]?.value;
        if (value is num) values.add(value.toDouble());
      }
    }
    if (values.isEmpty) return '--';
    final average = values.fold<double>(0, (sum, value) => sum + value) /
        values.length;
    return '${average.toStringAsFixed(1)} V';
  }

  String _highestTemperature(List<AssetSnapshot> devices) {
    final values = <double>[];
    for (final device in devices) {
      for (final entry in device.telemetry.entries) {
        final unit = normaliseUnit(entry.value.unit);
        final lower = '${entry.key}_${entry.value.nameEn ?? ''}'.toLowerCase();
        if (unit == '°C' &&
            (lower.contains('temp') || lower.contains('temperature'))) {
          final value = entry.value.value;
          if (value is num) values.add(value.toDouble());
        }
      }
    }
    if (values.isEmpty) return '--';
    values.sort();
    return '${values.last.toStringAsFixed(1)} °C';
  }
}
