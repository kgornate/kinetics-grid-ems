import 'package:flutter/material.dart';

import '../core/presentation/telemetry_presentation.dart';
import '../core/state/gateway_controller.dart';
import '../models/gateway_models.dart';
import '../widgets/common_widgets.dart';
import 'bau_screen.dart';
import 'environment_asset_screen.dart';
import 'pcs_detail_screen.dart';
import 'rack_detail_screen.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key, required this.controller});

  final GatewayController controller;

  @override
  Widget build(BuildContext context) {
    final bank = controller.plant.bank;
    final racks = controller.plant.racks;
    final environments = controller.plant.environment;
    final pcsDevices = controller.plant.pcsDevices;
    final onlineAssets = controller.plant.assets.values.where((asset) => asset.online).length;
    final effectiveVoltage = _effectiveBankVoltage(bank, racks);
    final effectiveCurrent = _effectiveBankCurrent(bank, racks);

    return RefreshIndicator(
      onRefresh: controller.refreshCompact,
      child: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          SectionHeader(
            'Plant overview',
            subtitle: '${controller.plant.gatewayId.isEmpty ? 'Gateway' : controller.plant.gatewayId} • ${controller.plant.mode.isEmpty ? '--' : controller.plant.mode} • sequence ${controller.plant.sequence}',
            trailing: Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                StatusPill(label: controller.restConnected ? 'REST connected' : 'REST offline', good: controller.restConnected, icon: Icons.http),
                StatusPill(label: controller.wsConnected ? 'Live stream' : 'Stream offline', good: controller.wsConnected, icon: Icons.sync),
              ],
            ),
          ),
          const SizedBox(height: 16),
          MetricGrid(
            children: [
              MetricTile(label: 'Bank voltage', value: effectiveVoltage.text, subtitle: effectiveVoltage.note, icon: Icons.bolt, emphasis: true),
              MetricTile(label: 'Bank current', value: effectiveCurrent.text, subtitle: effectiveCurrent.note, icon: Icons.electric_meter, emphasis: true),
              _bankMetric(bank, 'soc', 'Bank SOC', Icons.battery_5_bar, emphasis: true),
              _bankMetric(bank, 'bank_soh', 'Bank SOH', Icons.favorite, emphasis: true),
              _bankMetric(bank, 'bank_chgable_power', 'Charge power limit', Icons.power_input),
              _bankMetric(bank, 'bank_dsgable_power', 'Discharge power limit', Icons.power),
              MetricTile(label: 'Assets online', value: '$onlineAssets/${controller.plant.assets.length}', icon: Icons.hub),
              MetricTile(label: 'Active alarms', value: '${controller.activeAlarms.length}', icon: Icons.warning_amber),
            ],
          ),
          const SizedBox(height: 24),
          SectionHeader('Battery system', subtitle: 'Bank-level BAU view and four rack/BCU assets'),
          const SizedBox(height: 12),
          if (bank != null)
            SizedBox(
              height: 190,
              child: RichAssetCard(
                asset: bank,
                title: 'BMS Bank / BAU',
                metrics: [
                  effectiveVoltage.text,
                  effectiveCurrent.text,
                  _shown(bank, 'soc', prefix: 'SOC '),
                  _shown(bank, 'bank_soh', prefix: 'SOH '),
                  _shown(bank, 'echg_avl', prefix: 'Chargeable '),
                  _shown(bank, 'edsg_avl', prefix: 'Dischargeable '),
                ],
                warningCount: _alarmCount(bank.assetId),
                onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => BauScreen(controller: controller))),
              ),
            ),
          const SizedBox(height: 12),
          LayoutBuilder(
            builder: (context, constraints) {
              final count = constraints.maxWidth > 1050 ? 2 : 1;
              return GridView.builder(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: count,
                  crossAxisSpacing: 12,
                  mainAxisSpacing: 12,
                  childAspectRatio: 2.35,
                ),
                itemCount: racks.length,
                itemBuilder: (context, index) {
                  final rack = racks[index];
                  return RichAssetCard(
                    asset: rack,
                    metrics: _rackMetrics(rack),
                    warningCount: _alarmCount(rack.assetId),
                    onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
                      builder: (_) => RackDetailScreen(controller: controller, rack: rack),
                    )),
                  );
                },
              );
            },
          ),
          const SizedBox(height: 24),
          SectionHeader('Environment and power assets', subtitle: 'Key live values exposed through the BMS Power/Environment endpoint'),
          const SizedBox(height: 12),
          LayoutBuilder(
            builder: (context, constraints) {
              final count = constraints.maxWidth > 1050 ? 3 : constraints.maxWidth > 650 ? 2 : 1;
              return GridView.builder(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: count,
                  crossAxisSpacing: 12,
                  mainAxisSpacing: 12,
                  childAspectRatio: 1.95,
                ),
                itemCount: environments.length,
                itemBuilder: (context, index) {
                  final asset = environments[index];
                  return RichAssetCard(
                    asset: asset,
                    metrics: environmentSummary(asset),
                    warningCount: _alarmCount(asset.assetId),
                    onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
                      builder: (_) => EnvironmentAssetScreen(asset: asset),
                    )),
                  );
                },
              );
            },
          ),
          const SizedBox(height: 24),
          SectionHeader(
            'Power conversion system',
            subtitle: 'Four Modbus RTU PCS units on one RS485 bus',
          ),
          const SizedBox(height: 12),
          if (pcsDevices.isEmpty)
            const Card(
              child: ListTile(
                leading: Icon(Icons.electrical_services),
                title: Text('No PCS devices received yet'),
              ),
            )
          else
            LayoutBuilder(
              builder: (context, constraints) {
                final count = constraints.maxWidth > 1050 ? 2 : 1;
                return GridView.builder(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: count,
                    crossAxisSpacing: 12,
                    mainAxisSpacing: 12,
                    childAspectRatio: 2.2,
                  ),
                  itemCount: pcsDevices.length,
                  itemBuilder: (context, index) {
                    final pcs = pcsDevices[index];
                    return RichAssetCard(
                      asset: pcs,
                      title: pcs.label ?? 'PCS ${pcs.unitId ?? index + 1}',
                      metrics: [
                        'RTU ID ${pcs.unitId ?? '--'}',
                        ...pcsSummary(pcs),
                      ],
                      warningCount: _alarmCount(pcs.assetId),
                      onTap: () => Navigator.of(context).push(
                        MaterialPageRoute<void>(
                          builder: (_) => PcsDetailScreen(
                            controller: controller,
                            assetId: pcs.assetId,
                          ),
                        ),
                      ),
                    );
                  },
                );
              },
            ),
          const SizedBox(height: 24),
          SectionHeader('Active alarms', subtitle: '${controller.activeAlarms.length} active alarms'),
          const SizedBox(height: 10),
          if (controller.activeAlarms.isEmpty)
            const Card(child: ListTile(leading: Icon(Icons.check_circle), title: Text('No active alarms')))
          else
            ...controller.activeAlarms.take(8).map((alarm) => Card(
                  child: ListTile(
                    leading: const Icon(Icons.warning_amber),
                    title: Text((alarm['message'] ?? alarm['alarm_key'] ?? 'Alarm').toString()),
                    subtitle: Text('${alarm['asset_id'] ?? '--'} • ${alarm['severity'] ?? '--'}'),
                  ),
                )),
          const SizedBox(height: 40),
        ],
      ),
    );
  }

  Widget _bankMetric(AssetSnapshot? bank, String key, String label, IconData icon, {bool emphasis = false}) {
    final point = bank?.telemetry[key];
    final shown = point == null
        ? const PresentedValue(value: '--', unit: '', valid: false)
        : presentPoint(bank!.assetType, key, point);
    return MetricTile(label: label, value: shown.text, subtitle: shown.note, icon: icon, emphasis: emphasis);
  }

  List<String> _rackMetrics(AssetSnapshot rack) => [
        _shown(rack, 'vrack', prefix: 'Voltage '),
        _shown(rack, 'irack', prefix: 'Current '),
        _shown(rack, 'soc', prefix: 'SOC '),
        _shown(rack, 'soh', prefix: 'SOH '),
        '${_shown(rack, 'vcell_min')}–${_shown(rack, 'vcell_max')} cells',
        _shown(rack, 'tcell_max', prefix: 'Max temp '),
        _shown(rack, 'ir', prefix: 'Insulation '),
      ];

  String _shown(AssetSnapshot asset, String key, {String prefix = ''}) {
    final point = asset.telemetry[key];
    if (point == null) return '';
    return '$prefix${presentPoint(asset.assetType, key, point).text}';
  }

  int _alarmCount(String assetId) => controller.activeAlarms.where((alarm) => alarm['asset_id']?.toString() == assetId).length;

  PresentedValue _effectiveBankVoltage(AssetSnapshot? bank, List<AssetSnapshot> racks) {
    final point = bank?.telemetry['bank_voltage'];
    if (point?.value is num && (point!.value as num) > 0) return presentPoint(bank!.assetType, 'bank_voltage', point);
    final values = racks.map((rack) => rack.telemetry['vrack']?.value).whereType<num>().where((value) => value > 0).toList();
    if (values.isEmpty) return const PresentedValue(value: '--', unit: 'V', valid: false);
    final average = values.fold<double>(0, (sum, value) => sum + value.toDouble()) / values.length;
    return PresentedValue(value: average.toStringAsFixed(1), unit: 'V', note: 'Derived from rack voltages; BAU register reports 0 V');
  }

  PresentedValue _effectiveBankCurrent(AssetSnapshot? bank, List<AssetSnapshot> racks) {
    final point = bank?.telemetry['ibank'];
    if (point?.value is num && (point!.value as num).abs() > 0) return presentPoint(bank!.assetType, 'ibank', point);
    final values = racks.map((rack) => rack.telemetry['irack']?.value).whereType<num>().toList();
    if (values.isEmpty) return const PresentedValue(value: '--', unit: 'A', valid: false);
    final sum = values.fold<double>(0, (total, value) => total + value.toDouble());
    return PresentedValue(value: sum.toStringAsFixed(1), unit: 'A', note: 'Sum of rack currents; BAU register reports 0 A');
  }
}

