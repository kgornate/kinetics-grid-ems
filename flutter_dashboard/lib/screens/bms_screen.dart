import 'package:flutter/material.dart';

import '../models/bms_telemetry.dart';
import '../services/bms_service.dart';
import '../widgets/status_indicator.dart';
import '../widgets/telemetry_card.dart';

class BmsScreen extends StatefulWidget {
  final String gatewayIp;
  final BmsTelemetry? initialTelemetry;

  const BmsScreen({
    super.key,
    required this.gatewayIp,
    this.initialTelemetry,
  });

  @override
  State<BmsScreen> createState() => _BmsScreenState();
}

class _BmsScreenState extends State<BmsScreen> {
  late BmsTelemetry? _telemetry;
  bool _busy = false;
  String _statusMessage = 'BMS screen ready';

  @override
  void initState() {
    super.initState();
    _telemetry = widget.initialTelemetry;
  }

  BmsService _service() => BmsService.forGateway(widget.gatewayIp);

  Future<void> _runCommand(
    String label,
    Future<BmsCommandResult> Function(BmsService service) action,
  ) async {
    setState(() {
      _busy = true;
      _statusMessage = 'Sending $label...';
    });

    try {
      final result = await action(_service());
      setState(() {
        if (result.telemetry != null) {
          _telemetry = result.telemetry;
        }
        _statusMessage = result.response.isOk
            ? '$label successful: ${result.response.message ?? ''}'
            : '$label failed: ${result.response.message ?? ''}';
      });
    } catch (e) {
      setState(() {
        _statusMessage = '$label failed: $e';
      });
    } finally {
      setState(() {
        _busy = false;
      });
    }
  }

  Future<void> _confirmAndRun(
    String title,
    String message,
    Future<BmsCommandResult> Function(BmsService service) action,
  ) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: Text(title),
          content: Text(message),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Send'),
            ),
          ],
        );
      },
    );

    if (confirmed == true) {
      await _runCommand(title, action);
    }
  }

  String _value(dynamic value) {
    if (value == null) return '--';
    final text = value.toString();
    return text.isEmpty ? '--' : text;
  }

  String _doubleValue(double? value, {int digits = 1}) {
    if (value == null) return '--';
    return value.toStringAsFixed(digits);
  }

  String _formatTime(DateTime? time) {
    if (time == null) return '--';
    return '${time.hour.toString().padLeft(2, '0')}:'
        '${time.minute.toString().padLeft(2, '0')}:'
        '${time.second.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final bms = _telemetry;

    return Scaffold(
      appBar: AppBar(
        title: const Text('BMS / BCU Asset'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 16),
            child: Center(
              child: Text(
                widget.gatewayIp,
                style: const TextStyle(fontWeight: FontWeight.bold),
              ),
            ),
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildHeaderCard(bms),
            const SizedBox(height: 16),
            _sectionHeader('Battery Overview'),
            const SizedBox(height: 10),
            _buildOverviewGrid(bms),
            const SizedBox(height: 20),
            _sectionHeader('Battery Health'),
            const SizedBox(height: 10),
            _buildHealthGrid(bms),
            const SizedBox(height: 20),
            _sectionHeader('Safety & Status'),
            const SizedBox(height: 10),
            _buildSafetyGrid(bms),
            const SizedBox(height: 20),
            _sectionHeader('Active Alarms'),
            const SizedBox(height: 10),
            _buildAlarmCard(bms),
            const SizedBox(height: 20),
            _sectionHeader('BMS Control Panel'),
            const SizedBox(height: 10),
            _buildControlPanel(),
          ],
        ),
      ),
    );
  }

  Widget _sectionHeader(String title) {
    return Text(
      title,
      style: Theme.of(context).textTheme.titleLarge?.copyWith(
            fontWeight: FontWeight.bold,
          ),
    );
  }

  Widget _buildHeaderCard(BmsTelemetry? bms) {
    return Card(
      elevation: 1,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: 12,
              runSpacing: 12,
              children: [
                StatusIndicator(
                  label: 'BMS Comm',
                  status: bms?.effectiveCommStatus,
                  active: bms?.isOnline ?? false,
                ),
                StatusIndicator(
                  label: 'BCU State',
                  status: bms?.bcuState,
                  active: bms != null &&
                      (bms.bcuState == null ||
                          bms.bcuState!.toLowerCase().contains('normal')),
                ),
                StatusIndicator(
                  label: 'Current State',
                  status: bms?.currentState,
                  active: bms?.currentState != null,
                ),
                StatusIndicator(
                  label: 'Alarms',
                  status: bms == null ? '--' : '${bms.alarmCount}',
                  active: bms != null && !bms.hasAlarms,
                ),
              ],
            ),
            const SizedBox(height: 12),
            Text(_statusMessage),
            if (_busy) ...[
              const SizedBox(height: 12),
              const LinearProgressIndicator(),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildOverviewGrid(BmsTelemetry? bms) {
    return _responsiveGrid([
      TelemetryCard(title: 'SOC', value: _doubleValue(bms?.socPercent), unit: '%', icon: Icons.battery_full),
      TelemetryCard(title: 'SOH', value: _doubleValue(bms?.sohPercent), unit: '%', icon: Icons.health_and_safety),
      TelemetryCard(title: 'Rack Voltage', value: _doubleValue(bms?.rackVoltageV), unit: 'V', icon: Icons.bolt),
      TelemetryCard(title: 'Rack Current', value: _doubleValue(bms?.rackCurrentA), unit: 'A', icon: Icons.electric_meter),
      TelemetryCard(title: 'Power', value: _doubleValue(bms?.powerKw, digits: 2), unit: 'kW', icon: Icons.power),
      TelemetryCard(title: 'Last Update', value: _formatTime(bms?.receivedAt), icon: Icons.access_time),
    ]);
  }

  Widget _buildHealthGrid(BmsTelemetry? bms) {
    return _responsiveGrid([
      TelemetryCard(title: 'Max Cell Voltage', value: _doubleValue(bms?.maxCellVoltageMv, digits: 0), unit: 'mV', icon: Icons.arrow_upward),
      TelemetryCard(title: 'Min Cell Voltage', value: _doubleValue(bms?.minCellVoltageMv, digits: 0), unit: 'mV', icon: Icons.arrow_downward),
      TelemetryCard(title: 'Cell Voltage Diff', value: _doubleValue(bms?.cellVoltageDiffMv, digits: 0), unit: 'mV', icon: Icons.compare_arrows),
      TelemetryCard(title: 'Max Temp', value: _doubleValue(bms?.maxCellTempC), unit: '°C', icon: Icons.device_thermostat),
      TelemetryCard(title: 'Min Temp', value: _doubleValue(bms?.minCellTempC), unit: '°C', icon: Icons.thermostat),
      TelemetryCard(title: 'Avg Temp', value: _doubleValue(bms?.avgTempC), unit: '°C', icon: Icons.thermostat_auto),
      TelemetryCard(title: 'Charge Limit', value: _doubleValue(bms?.maxAllowedChargeCurrentA), unit: 'A', icon: Icons.input),
      TelemetryCard(title: 'Discharge Limit', value: _doubleValue(bms?.maxAllowedDischargeCurrentA), unit: 'A', icon: Icons.output),
    ]);
  }

  Widget _buildSafetyGrid(BmsTelemetry? bms) {
    return _responsiveGrid([
      TelemetryCard(title: 'Insulation', value: _doubleValue(bms?.insulationResistanceKohm, digits: 0), unit: 'kΩ', icon: Icons.security),
      TelemetryCard(title: 'Positive IR', value: _doubleValue(bms?.positiveInsulationResistanceKohm, digits: 0), unit: 'kΩ', icon: Icons.add_circle_outline),
      TelemetryCard(title: 'Negative IR', value: _doubleValue(bms?.negativeInsulationResistanceKohm, digits: 0), unit: 'kΩ', icon: Icons.remove_circle_outline),
      TelemetryCard(title: 'Precharge Stage', value: _value(bms?.prechargeStage), icon: Icons.offline_bolt),
      TelemetryCard(title: 'Positive Contactor', value: bms == null ? '--' : (bms.positiveContactorClosed ? 'Closed' : 'Open'), icon: Icons.check_circle),
      TelemetryCard(title: 'Negative Contactor', value: bms == null ? '--' : (bms.negativeContactorClosed ? 'Closed' : 'Open'), icon: Icons.check_circle_outline),
    ]);
  }

  Widget _buildAlarmCard(BmsTelemetry? bms) {
    final alarms = bms?.activeAlarms ?? const <String>[];

    return Card(
      elevation: 1,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: alarms.isEmpty
            ? const Text('No active BMS alarms')
            : Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: alarms
                    .map(
                      (alarm) => Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Icon(Icons.warning_amber, size: 18),
                            const SizedBox(width: 8),
                            Expanded(child: Text(alarm)),
                          ],
                        ),
                      ),
                    )
                    .toList(),
              ),
      ),
    );
  }

  Widget _buildControlPanel() {
    return Card(
      elevation: 1,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            FilledButton(
              onPressed: _busy ? null : () => _runCommand('Read BMS', (service) => service.readAll()),
              child: const Text('Read BMS'),
            ),
            FilledButton.tonal(
              onPressed: _busy ? null : () => _runCommand('Read Alarms', (service) => service.readAlarms()),
              child: const Text('Read Alarms'),
            ),
            FilledButton(
              onPressed: _busy
                  ? null
                  : () => _confirmAndRun(
                        'Start Precharge',
                        'Send START_BMS_PRECHARGE command to BMS?',
                        (service) => service.startPrecharge(),
                      ),
              child: const Text('Start Precharge'),
            ),
            FilledButton.tonal(
              onPressed: _busy
                  ? null
                  : () => _confirmAndRun(
                        'Stop Precharge',
                        'Send STOP_BMS_PRECHARGE command to BMS?',
                        (service) => service.stopPrecharge(),
                      ),
              child: const Text('Stop Precharge'),
            ),
            FilledButton.tonal(
              onPressed: _busy
                  ? null
                  : () => _confirmAndRun(
                        'Start Insulation Test',
                        'Send START_BMS_INSULATION_TEST command to BMS?',
                        (service) => service.startInsulationTest(),
                      ),
              child: const Text('Start Insulation Test'),
            ),
            FilledButton.tonal(
              onPressed: _busy ? null : () => _runCommand('Fan Auto', (service) => service.fanAuto()),
              child: const Text('Fan Auto'),
            ),
            FilledButton.tonal(
              onPressed: _busy ? null : () => _runCommand('Fan ON', (service) => service.fanOn()),
              child: const Text('Fan ON'),
            ),
            FilledButton.tonal(
              onPressed: _busy ? null : () => _runCommand('Fan OFF', (service) => service.fanOff()),
              child: const Text('Fan OFF'),
            ),
            FilledButton.tonal(
              onPressed: _busy
                  ? null
                  : () => _confirmAndRun(
                        'Reset BCU',
                        'This will send RESET_BCU command. Continue?',
                        (service) => service.resetBcu(),
                      ),
              child: const Text('Reset BCU'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _responsiveGrid(List<Widget> children) {
    return LayoutBuilder(
      builder: (context, constraints) {
        int crossAxisCount = 3;
        if (constraints.maxWidth < 900) crossAxisCount = 2;
        if (constraints.maxWidth < 560) crossAxisCount = 1;

        return GridView.count(
          crossAxisCount: crossAxisCount,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          childAspectRatio: 2.35,
          crossAxisSpacing: 12,
          mainAxisSpacing: 12,
          children: children,
        );
      },
    );
  }
}
