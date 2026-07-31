import 'dart:convert';

import 'package:flutter/material.dart';

import '../core/state/gateway_controller.dart';
import '../models/gateway_models.dart';
import '../widgets/common_widgets.dart';

class ControlSequenceScreen extends StatefulWidget {
  const ControlSequenceScreen({super.key, required this.controller});

  final GatewayController controller;

  @override
  State<ControlSequenceScreen> createState() => _ControlSequenceScreenState();
}

class _ControlSequenceScreenState extends State<ControlSequenceScreen> {
  final TextEditingController _power = TextEditingController(text: '0');
  final TextEditingController _rampStep = TextEditingController(text: '10');
  final TextEditingController _rampInterval = TextEditingController(text: '1');
  String _direction = 'charge';

  @override
  void initState() {
    super.initState();
    // HomeShell starts polling only while the Control destination is visible.
    // The screen may exist offstage inside IndexedStack, so it must not own a
    // background timer by itself.
  }

  @override
  void dispose() {
    widget.controller.stopControlPolling();
    _power.dispose();
    _rampStep.dispose();
    _rampInterval.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: widget.controller,
      builder: (context, _) {
        final controller = widget.controller;
        final capabilities = controller.controlCapabilities;
        final status = controller.controlStatus;
        if (!controller.isInternal) {
          return const Center(
            child: Text('Internal role is required for BESS sequence control.'),
          );
        }
        return ListView(
          padding: const EdgeInsets.all(20),
          children: [
            SectionHeader(
              'BESS control sequence',
              subtitle:
                  'Independent Pair 1–4 startup, charge/discharge and pair-safe shutdown. Each pair uses BAU 0x3001 on its own BMS TCP port while the gateway verifies BCU and PCS feedback.',
              trailing: FilledButton.tonalIcon(
                onPressed: controller.controlBusy
                    ? null
                    : () async {
                        await controller.refreshControlCapabilities();
                        await controller.refreshControlStatus();
                        await controller.refreshSelectedControlStatusFresh();
                      },
                icon: const Icon(Icons.refresh),
                label: const Text('Refresh'),
              ),
            ),
            const SizedBox(height: 14),
            _GateBanner(
              controller: controller,
              capabilities: capabilities,
              status: status,
            ),
            const SizedBox(height: 14),
            _PairOverview(
              controller: controller,
              capabilities: capabilities,
            ),
            const SizedBox(height: 14),
            _SystemStateCard(status: status),
            const SizedBox(height: 14),
            _MetricPanel(status: status),
            const SizedBox(height: 20),
            _CommandPanel(
              controller: controller,
              capabilities: capabilities,
              status: status,
              direction: _direction,
              powerController: _power,
              rampStepController: _rampStep,
              rampIntervalController: _rampInterval,
              onDirectionChanged: (value) => setState(() => _direction = value),
              onAutomatic: _automaticStart,
              onNextStep: _nextStep,
              onSetPower: _setPower,
              onZero: _zeroPower,
              onSafeStop: _safeStop,
              onSafeStopAll: _safeStopAll,
              onAbort: _abort,
            ),
            const SizedBox(height: 20),
            _SequenceSteps(status: status),
            if (controller.lastEventMessage != null) ...[
              const SizedBox(height: 14),
              Card(
                child: ListTile(
                  leading: const Icon(Icons.check_circle_outline),
                  title: const Text('Latest control event'),
                  subtitle: Text(controller.lastEventMessage!),
                ),
              ),
            ],
            if (controller.errorMessage != null) ...[
              const SizedBox(height: 14),
              Card(
                color: Theme.of(context).colorScheme.errorContainer,
                child: ListTile(
                  leading: const Icon(Icons.error_outline),
                  title: const Text('Control error'),
                  subtitle: SelectableText(controller.errorMessage!),
                ),
              ),
            ],
            if (controller.lastControlResponse.isNotEmpty) ...[
              const SizedBox(height: 14),
              Card(
                child: ExpansionTile(
                  title: const Text('Latest gateway response'),
                  subtitle: Text(
                    controller.lastControlResponse['stage']?.toString() ??
                        controller.lastControlResponse['run_id']?.toString() ??
                        'Response details',
                  ),
                  children: [
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                      child: SelectableText(
                        const JsonEncoder.withIndent('  ')
                            .convert(controller.lastControlResponse),
                        style: const TextStyle(fontFamily: 'monospace'),
                      ),
                    ),
                  ],
                ),
              ),
            ],
            const SizedBox(height: 40),
          ],
        );
      },
    );
  }

  double _readPositive(TextEditingController controller, String label) {
    final value = double.tryParse(controller.text.trim());
    if (value == null || value < 0) {
      throw FormatException('$label must be a non-negative number.');
    }
    return value;
  }

  Future<bool> _confirm(String title, String message, {bool dangerous = false}) async {
    return await showDialog<bool>(
          context: context,
          barrierDismissible: false,
          builder: (context) => AlertDialog(
            icon: Icon(dangerous ? Icons.warning_amber : Icons.fact_check),
            title: Text(title),
            content: Text(message),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('Cancel'),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(context, true),
                child: const Text('Execute'),
              ),
            ],
          ),
        ) ??
        false;
  }

  Future<void> _automaticStart() async {
    try {
      final power = _readPositive(_power, 'Power');
      final step = _readPositive(_rampStep, 'Ramp step');
      final interval = _readPositive(_rampInterval, 'Ramp interval');
      final confirmed = await _confirm(
        'Start automatic sequence?',
        'The gateway will configure the selected PCS, connect its pair-specific BAU through 0x3001, verify BCU precharge/contactors, start the PCS at 0 kW and ramp to ${_direction == 'charge' ? '-' : '+'}${power.toStringAsFixed(1)} kW. Keep the physical E-stop accessible.',
        dangerous: true,
      );
      if (!confirmed) return;
      await widget.controller.automaticStart(
        direction: _direction,
        targetPowerKw: power,
        rampStepKw: step,
        rampIntervalSeconds: interval,
      );
    } catch (error) {
      _showError(error);
    }
  }

  Future<void> _nextStep() async {
    try {
      final power = _readPositive(_power, 'Power');
      final confirmed = await _confirm(
        'Execute next commissioning step?',
        'The gateway will infer and execute only the next valid stage, then verify its feedback.',
      );
      if (!confirmed) return;
      await widget.controller.nextControlStep(
        direction: _direction,
        targetPowerKw: power,
      );
    } catch (error) {
      _showError(error);
    }
  }

  Future<void> _setPower() async {
    try {
      final power = _readPositive(_power, 'Power');
      final sign = _direction == 'charge' ? '-' : '+';
      final confirmed = await _confirm(
        'Apply $sign${power.toStringAsFixed(1)} kW?',
        'This command is allowed only after the gateway confirms PCS DC readiness, BMS limits and direction permission.',
        dangerous: power > 0,
      );
      if (!confirmed) return;
      await widget.controller.setControlPower(
        direction: _direction,
        powerKw: power,
      );
    } catch (error) {
      _showError(error);
    }
  }

  Future<void> _zeroPower() async {
    final confirmed = await _confirm(
      'Return to zero power?',
      'The gateway will command and verify a 0 kW PCS setpoint.',
    );
    if (!confirmed) return;
    try {
      await widget.controller.zeroControlPower();
    } catch (error) {
      _showError(error);
    }
  }

  Future<void> _safeStop() async {
    final confirmed = await _confirm(
      'Complete safe shutdown?',
      'The gateway will quiesce this pair’s runtime monitor, return the PCS to 0 kW, stop it, write BAU 0x3001 = 2 on this pair’s BMS port and verify both main contactors open.',
      dangerous: true,
    );
    if (!confirmed) return;
    try {
      await widget.controller.safeStopControl(openBms: true);
    } catch (error) {
      _showError(error);
    }
  }

  Future<void> _safeStopAll() async {
    final confirmed = await _confirm(
      'Safe-stop every enabled pair?',
      'The gateway will process pairs sequentially. For each pair it will command 0 kW, verify actual power is zero, stop the PCS, then cut off only that pair’s BAU 0x3001 and verify its contactors open.',
      dangerous: true,
    );
    if (!confirmed) return;
    try {
      await widget.controller.safeStopAllControl(openBms: true);
    } catch (error) {
      _showError(error);
    }
  }

  Future<void> _abort() async {
    final confirmed = await _confirm(
      'Abort active sequence?',
      'The gateway will cancel the automatic run and execute a complete safe shutdown.',
      dangerous: true,
    );
    if (!confirmed) return;
    try {
      await widget.controller.abortControl(openBms: true);
    } catch (error) {
      _showError(error);
    }
  }

  void _showError(Object error) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(error.toString())),
    );
  }
}

class _PairOverview extends StatelessWidget {
  const _PairOverview({
    required this.controller,
    required this.capabilities,
  });

  final GatewayController controller;
  final ControlSequenceCapabilities? capabilities;

  @override
  Widget build(BuildContext context) {
    final pairs = capabilities?.pairs.where((pair) => pair.enabled).toList() ??
        const <ControlPairSummary>[];
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    'Multi-pair live overview',
                    style: Theme.of(context)
                        .textTheme
                        .titleLarge
                        ?.copyWith(fontWeight: FontWeight.w800),
                  ),
                ),
                Text(
                  'Plant setpoint ${controller.totalControlSetpointKw.toStringAsFixed(1)} kW  •  '
                  'actual ${controller.totalControlActualPowerKw.toStringAsFixed(1)} kW',
                ),
              ],
            ),
            const SizedBox(height: 12),
            if (pairs.isEmpty)
              const Text('Waiting for enabled control pairs...')
            else
              Wrap(
                spacing: 10,
                runSpacing: 10,
                children: pairs.map((pair) {
                  final status = controller.controlStatusFor(pair.pairId);
                  final actual = status?.value('pcs_actual_power_kw');
                  final setpoint = status?.value('pcs_power_setpoint_kw');
                  final pcsState = status?.value('pcs_operating_state');
                  final precharge = status?.value('precharge_state');
                  final fault = status?.flag('pcs_fault_shutdown') == true ||
                      status?.hardBlocked == true;
                  final refresh = status?.raw['refresh'];
                  final source = refresh is Map
                      ? refresh['source']?.toString() ?? 'cache'
                      : 'cache';
                  final stale = refresh is Map && refresh['stale'] == true;
                  final selected = pair.pairId == controller.selectedControlPair;
                  final busy = controller.isControlPairBusy(pair.pairId);
                  return SizedBox(
                    width: 245,
                    child: InkWell(
                      borderRadius: BorderRadius.circular(12),
                      onTap: () => controller.selectControlPair(pair.pairId),
                      child: Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                            color: selected
                                ? Theme.of(context).colorScheme.primary
                                : Theme.of(context).dividerColor,
                            width: selected ? 2 : 1,
                          ),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Expanded(
                                  child: Text(
                                    '${pair.pairId} • Rack ${pair.rackId} / ${pair.pcsAssetId}',
                                    style: const TextStyle(fontWeight: FontWeight.w700),
                                  ),
                                ),
                                if (busy)
                                  const SizedBox(
                                    width: 16,
                                    height: 16,
                                    child: CircularProgressIndicator(strokeWidth: 2),
                                  )
                                else
                                  Icon(
                                    fault ? Icons.error : Icons.check_circle,
                                    size: 18,
                                    color: fault
                                        ? Theme.of(context).colorScheme.error
                                        : Theme.of(context).colorScheme.primary,
                                  ),
                              ],
                            ),
                            const SizedBox(height: 6),
                            Text(
                              'Set ${setpoint?.toStringAsFixed(1) ?? '--'} kW  •  '
                              'Actual ${actual?.toStringAsFixed(1) ?? '--'} kW',
                            ),
                            Text(
                              'PCS ${pcsState?.toStringAsFixed(0) ?? '--'}  •  '
                              'Precharge ${precharge?.toStringAsFixed(0) ?? '--'}',
                            ),
                            Text(
                              '${stale ? 'STALE • ' : ''}$source',
                              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                    color: stale
                                        ? Theme.of(context).colorScheme.error
                                        : Theme.of(context).colorScheme.onSurfaceVariant,
                                  ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  );
                }).toList(),
              ),
          ],
        ),
      ),
    );
  }
}

class _GateBanner extends StatelessWidget {
  const _GateBanner({
    required this.controller,
    required this.capabilities,
    required this.status,
  });

  final GatewayController controller;
  final ControlSequenceCapabilities? capabilities;
  final ControlSequenceStatus? status;

  @override
  Widget build(BuildContext context) {
    final stageEnabled = capabilities?.enabled == true && status?.controlEnabled == true;
    final automatic = capabilities?.fullAutomaticAllowed == true;
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        StatusPill(
          label: stageEnabled ? 'Staged writes armed' : 'Control writes blocked',
          good: stageEnabled,
          icon: Icons.security,
        ),
        StatusPill(
          label: automatic ? 'Automatic mode enabled' : 'Automatic mode disabled',
          good: automatic,
          icon: Icons.auto_mode,
        ),
        StatusPill(
          label: status?.hardBlocked == true ? 'Hard safety blocker active' : 'No hard safety blocker',
          good: status?.hardBlocked != true,
          icon: Icons.health_and_safety,
        ),
        StatusPill(
          label: status?.errors.isEmpty == true
              ? 'All required reads good'
              : 'Read errors present',
          good: status?.errors.isEmpty == true,
          icon: Icons.sensors,
        ),
        StatusPill(
          label: controller.controlStatusIsStale
              ? 'Control telemetry stale'
              : 'Control telemetry fresh',
          good: !controller.controlStatusIsStale,
          icon: Icons.schedule,
        ),
        StatusPill(
          label: 'Source: ${controller.controlStatusSource}',
          good: !controller.controlStatusIsStale,
          icon: Icons.cached,
        ),
        StatusPill(
          label: controller.controlPollingActive
              ? 'Visible-screen polling active'
              : 'Control polling paused',
          good: true,
          icon: Icons.visibility,
        ),
      ],
    );
  }
}

class _SystemStateCard extends StatelessWidget {
  const _SystemStateCard({required this.status});

  final ControlSequenceStatus? status;

  @override
  Widget build(BuildContext context) {
    final state = status?.systemState ?? 'loading';
    final run = status?.runStatus ?? 'idle';
    final good = status != null && !status!.hardBlocked;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Row(
          children: [
            CircleAvatar(
              radius: 26,
              child: Icon(_stateIcon(state)),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _humanize(state),
                    style: Theme.of(context)
                        .textTheme
                        .headlineSmall
                        ?.copyWith(fontWeight: FontWeight.w800),
                  ),
                  Text(
                    'Automatic run: ${_humanize(run)}${status?.runId == null ? '' : ' • ${status!.runId}'}',
                  ),
                  Text(
                    status?.timestamp == null
                        ? 'Control status timestamp unavailable'
                        : 'Control status: ${status!.timestamp}',
                  ),
                  if (status?.lastError != null)
                    Text(
                      status!.lastError!,
                      style: TextStyle(color: Theme.of(context).colorScheme.error),
                    ),
                ],
              ),
            ),
            StatusPill(
              label: status?.readyForPower == true ? 'Ready for power' : 'Not power-ready',
              good: status?.readyForPower == true && good,
              icon: Icons.electric_bolt,
            ),
          ],
        ),
      ),
    );
  }

  IconData _stateIcon(String state) {
    if (state == 'charging') return Icons.battery_charging_full;
    if (state == 'discharging') return Icons.outbound;
    if (state == 'ready_zero_power') return Icons.check_circle;
    if (state == 'stopped_safe') return Icons.power_settings_new;
    return Icons.sync;
  }
}

class _MetricPanel extends StatelessWidget {
  const _MetricPanel({required this.status});

  final ControlSequenceStatus? status;

  @override
  Widget build(BuildContext context) {
    String number(String key, String unit, {int decimals = 1}) {
      final value = status?.value(key);
      return value == null ? '--' : '${value.toStringAsFixed(decimals)} $unit';
    }

    return MetricGrid(
      minWidth: 205,
      children: [
        MetricTile(
          label: 'PCS setpoint',
          value: number('pcs_power_setpoint_kw', 'kW'),
          icon: Icons.tune,
          emphasis: true,
        ),
        MetricTile(
          label: 'PCS actual power',
          value: number('pcs_actual_power_kw', 'kW'),
          icon: Icons.show_chart,
          emphasis: true,
        ),
        MetricTile(
          label: 'Rack voltage',
          value: number('rack_voltage_v', 'V'),
          icon: Icons.battery_full,
        ),
        MetricTile(
          label: 'PCS input voltage',
          value: number('pcs_battery_voltage_v', 'V'),
          icon: Icons.input,
        ),
        MetricTile(
          label: 'PCS DC bus',
          value: number('pcs_dc_bus_voltage_v', 'V'),
          icon: Icons.electric_meter,
        ),
        MetricTile(
          label: 'Charge limit',
          value: number('bms_charge_power_limit_kw', 'kW'),
          subtitle: number('rack_charge_current_limit_a', 'A'),
          icon: Icons.south_west,
        ),
        MetricTile(
          label: 'Discharge limit',
          value: number('bms_discharge_power_limit_kw', 'kW'),
          subtitle: number('rack_discharge_current_limit_a', 'A'),
          icon: Icons.north_east,
        ),
        MetricTile(
          label: 'PCS state bitfield',
          value: number('pcs_operating_state', '', decimals: 0).trim(),
          subtitle: status?.flag('pcs_dc_breaker_feedback_closed') == true
              ? 'DC breaker closed'
              : 'DC breaker open',
          icon: Icons.memory,
        ),
      ],
    );
  }
}

class _CommandPanel extends StatelessWidget {
  const _CommandPanel({
    required this.controller,
    required this.capabilities,
    required this.status,
    required this.direction,
    required this.powerController,
    required this.rampStepController,
    required this.rampIntervalController,
    required this.onDirectionChanged,
    required this.onAutomatic,
    required this.onNextStep,
    required this.onSetPower,
    required this.onZero,
    required this.onSafeStop,
    required this.onSafeStopAll,
    required this.onAbort,
  });

  final GatewayController controller;
  final ControlSequenceCapabilities? capabilities;
  final ControlSequenceStatus? status;
  final String direction;
  final TextEditingController powerController;
  final TextEditingController rampStepController;
  final TextEditingController rampIntervalController;
  final ValueChanged<String> onDirectionChanged;
  final VoidCallback onAutomatic;
  final VoidCallback onNextStep;
  final VoidCallback onSetPower;
  final VoidCallback onZero;
  final VoidCallback onSafeStop;
  final VoidCallback onSafeStopAll;
  final VoidCallback onAbort;

  @override
  Widget build(BuildContext context) {
    final enabled = status?.controlEnabled == true && !controller.controlBusy;
    final automaticEnabled = enabled && capabilities?.fullAutomaticAllowed == true;
    final pairs = capabilities?.pairs.where((pair) => pair.enabled).toList() ??
        const <ControlPairSummary>[];
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Operator commands',
              style: Theme.of(context)
                  .textTheme
                  .titleLarge
                  ?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 14),
            Wrap(
              spacing: 12,
              runSpacing: 12,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                SizedBox(
                  width: 190,
                  child: DropdownButtonFormField<String>(
                    initialValue: controller.selectedControlPair,
                    decoration: const InputDecoration(
                      labelText: 'BMS–PCS pair',
                      border: OutlineInputBorder(),
                    ),
                    items: pairs
                        .map((pair) => DropdownMenuItem<String>(
                              value: pair.pairId,
                              child: Text(
                                  '${pair.pairId}: Rack ${pair.rackId} / ${pair.pcsAssetId}'),
                            ))
                        .toList(),
                    onChanged: enabled
                        ? (value) {
                            if (value != null) controller.selectControlPair(value);
                          }
                        : null,
                  ),
                ),
                SegmentedButton<String>(
                  segments: const [
                    ButtonSegment(
                      value: 'charge',
                      label: Text('Charge'),
                      icon: Icon(Icons.south_west),
                    ),
                    ButtonSegment(
                      value: 'discharge',
                      label: Text('Discharge'),
                      icon: Icon(Icons.north_east),
                    ),
                  ],
                  selected: <String>{direction},
                  onSelectionChanged: enabled
                      ? (value) => onDirectionChanged(value.first)
                      : null,
                ),
                SizedBox(
                  width: 150,
                  child: TextField(
                    controller: powerController,
                    enabled: enabled,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                      labelText: 'Target power',
                      suffixText: 'kW',
                      border: OutlineInputBorder(),
                    ),
                  ),
                ),
                SizedBox(
                  width: 135,
                  child: TextField(
                    controller: rampStepController,
                    enabled: automaticEnabled,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                      labelText: 'Ramp step',
                      suffixText: 'kW',
                      border: OutlineInputBorder(),
                    ),
                  ),
                ),
                SizedBox(
                  width: 145,
                  child: TextField(
                    controller: rampIntervalController,
                    enabled: automaticEnabled,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                      labelText: 'Ramp interval',
                      suffixText: 's',
                      border: OutlineInputBorder(),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 14),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                FilledButton.icon(
                  onPressed: automaticEnabled ? onAutomatic : null,
                  icon: controller.controlBusy
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.auto_mode),
                  label: const Text('Start automatic ramp'),
                ),
                FilledButton.tonalIcon(
                  onPressed: enabled ? onNextStep : null,
                  icon: const Icon(Icons.skip_next),
                  label: const Text('Execute next step'),
                ),
                FilledButton.tonalIcon(
                  onPressed: enabled && status?.readyForPower == true
                      ? onSetPower
                      : null,
                  icon: const Icon(Icons.speed),
                  label: const Text('Set power directly'),
                ),
                OutlinedButton.icon(
                  onPressed: enabled ? onZero : null,
                  icon: const Icon(Icons.exposure_zero),
                  label: const Text('Zero power'),
                ),
                FilledButton.icon(
                  style: FilledButton.styleFrom(
                    backgroundColor: Theme.of(context).colorScheme.error,
                    foregroundColor: Theme.of(context).colorScheme.onError,
                  ),
                  onPressed: enabled ? onSafeStop : null,
                  icon: const Icon(Icons.power_settings_new),
                  label: const Text('Safe shutdown'),
                ),
                OutlinedButton.icon(
                  onPressed: controller.anyControlBusy ? null : onSafeStopAll,
                  icon: const Icon(Icons.power_off),
                  label: const Text('Safe stop all pairs'),
                ),
                OutlinedButton.icon(
                  onPressed: enabled && status?.automaticRunning == true
                      ? onAbort
                      : null,
                  icon: const Icon(Icons.cancel),
                  label: const Text('Abort sequence'),
                ),
              ],
            ),
            if (capabilities?.fullAutomaticAllowed != true) ...[
              const SizedBox(height: 10),
              const Text(
                'Automatic mode is intentionally configuration-gated. Commissioning “Execute next step”, set-power, zero-power and safe-shutdown remain available when staged writes are armed.',
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _SequenceSteps extends StatelessWidget {
  const _SequenceSteps({required this.status});

  final ControlSequenceStatus? status;

  @override
  Widget build(BuildContext context) {
    final automatic = status?.runSteps ?? const <ControlSequenceStep>[];
    final steps = automatic.isNotEmpty
        ? automatic
        : status?.workflowSteps ?? const <ControlSequenceStep>[];
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              automatic.isNotEmpty
                  ? 'Automatic sequence progress'
                  : 'Validated startup readiness',
              style: Theme.of(context)
                  .textTheme
                  .titleLarge
                  ?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 10),
            if (steps.isEmpty)
              const Text('Waiting for control-sequence status...')
            else
              ...steps.map((step) => ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: _StepIcon(step: step),
                    title: Text(step.label),
                    subtitle: step.message == null ? null : Text(step.message!),
                    trailing: Text(_humanize(step.status)),
                  )),
          ],
        ),
      ),
    );
  }
}

class _StepIcon extends StatelessWidget {
  const _StepIcon({required this.step});

  final ControlSequenceStep step;

  @override
  Widget build(BuildContext context) {
    if (step.failed) {
      return Icon(Icons.cancel, color: Theme.of(context).colorScheme.error);
    }
    if (step.running) return const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2));
    if (step.complete) {
      return Icon(Icons.check_circle, color: Theme.of(context).colorScheme.primary);
    }
    return const Icon(Icons.radio_button_unchecked);
  }
}

String _humanize(String value) {
  if (value.isEmpty) return '--';
  return value
      .replaceAll('_', ' ')
      .split(' ')
      .where((part) => part.isNotEmpty)
      .map((part) => '${part[0].toUpperCase()}${part.substring(1)}')
      .join(' ');
}
