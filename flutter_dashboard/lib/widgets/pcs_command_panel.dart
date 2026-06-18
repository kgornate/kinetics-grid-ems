import 'package:flutter/material.dart';
import '../features/commands/commands.dart';

class PcsCommandPanel extends StatefulWidget {
  final Future<void> Function(String command, {dynamic value}) onSendCommand;

  const PcsCommandPanel({
    super.key,
    required this.onSendCommand,
  });

  @override
  State<PcsCommandPanel> createState() => _PcsCommandPanelState();
}

class _PcsCommandPanelState extends State<PcsCommandPanel> {
  final TextEditingController _activePowerController =
      TextEditingController(text: '0');
  final TextEditingController _reactivePowerController =
      TextEditingController(text: '0');
  final TextEditingController _heartbeatController =
      TextEditingController(text: '1');

  @override
  void dispose() {
    _activePowerController.dispose();
    _reactivePowerController.dispose();
    _heartbeatController.dispose();
    super.dispose();
  }

  Future<void> _sendCommand(String command, {dynamic value}) async {
    await widget.onSendCommand(command, value: value);
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 1,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'PCS Command Panel',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            Text(
              'Use this panel only after PCS AC/DC wiring, BMS interlocks, EPO and site safety are confirmed.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 18),
            _sectionTitle(context, 'Read / Refresh'),
            const SizedBox(height: 12),
            _buildReadCommands(),
            const SizedBox(height: 18),
            const Divider(),
            const SizedBox(height: 14),
            _sectionTitle(context, 'Power Setpoints'),
            const SizedBox(height: 12),
            _buildActivePowerCommand(),
            const SizedBox(height: 14),
            _buildReactivePowerCommand(),
            const SizedBox(height: 18),
            const Divider(),
            const SizedBox(height: 14),
            _sectionTitle(context, 'Communication / Heartbeat'),
            const SizedBox(height: 12),
            _buildHeartbeatCommand(),
            const SizedBox(height: 18),
            const Divider(),
            const SizedBox(height: 14),
            _sectionTitle(context, 'Operational Commands'),
            const SizedBox(height: 12),
            _buildPowerCommands(),
          ],
        ),
      ),
    );
  }

  Widget _sectionTitle(BuildContext context, String title) {
    return Text(
      title,
      style: Theme.of(context).textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.bold,
          ),
    );
  }

  Widget _buildReadCommands() {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: [
        FilledButton(
          onPressed: () => _sendCommand(GatewayCommandNames.readPcs),
          child: const Text('Read PCS'),
        ),
        FilledButton.tonal(
          onPressed: () => _sendCommand(GatewayCommandNames.readAllAssets),
          child: const Text('Read All Assets'),
        ),
        FilledButton.tonal(
          onPressed: () => _sendCommand(GatewayCommandNames.status),
          child: const Text('Gateway Status'),
        ),
      ],
    );
  }

  Widget _buildActivePowerCommand() {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        SizedBox(
          width: 230,
          child: TextField(
            controller: _activePowerController,
            decoration: const InputDecoration(
              labelText: 'PCS Active Power',
              suffixText: 'kW',
              helperText: '+ve discharge, -ve charge. Use 0 for safe test.',
              border: OutlineInputBorder(),
              isDense: true,
            ),
            keyboardType: const TextInputType.numberWithOptions(
              decimal: true,
              signed: true,
            ),
          ),
        ),
        SizedBox(
          width: 140,
          height: 44,
          child: FilledButton(
            onPressed: () {
              final value = double.tryParse(_activePowerController.text.trim());
              if (value == null) {
                _showMessage('Invalid PCS active power value');
                return;
              }
              _confirmAndSendValue(
                title: 'Confirm PCS Active Power',
                message: 'Send PCS_SET_ACTIVE_POWER = $value kW?',
                command: GatewayCommandNames.setPcsActivePower,
                value: value,
              );
            },
            child: const Text('Set kW'),
          ),
        ),
      ],
    );
  }

  Widget _buildReactivePowerCommand() {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        SizedBox(
          width: 230,
          child: TextField(
            controller: _reactivePowerController,
            decoration: const InputDecoration(
              labelText: 'PCS Reactive Power',
              suffixText: 'kvar',
              helperText: 'Use 0 for safe test.',
              border: OutlineInputBorder(),
              isDense: true,
            ),
            keyboardType: const TextInputType.numberWithOptions(
              decimal: true,
              signed: true,
            ),
          ),
        ),
        SizedBox(
          width: 140,
          height: 44,
          child: FilledButton.tonal(
            onPressed: () {
              final value = double.tryParse(_reactivePowerController.text.trim());
              if (value == null) {
                _showMessage('Invalid PCS reactive power value');
                return;
              }
              _confirmAndSendValue(
                title: 'Confirm PCS Reactive Power',
                message: 'Send PCS_SET_REACTIVE_POWER = $value kvar?',
                command: GatewayCommandNames.setPcsReactivePower,
                value: value,
              );
            },
            child: const Text('Set kvar'),
          ),
        ),
      ],
    );
  }

  Widget _buildHeartbeatCommand() {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        SizedBox(
          width: 230,
          child: TextField(
            controller: _heartbeatController,
            decoration: const InputDecoration(
              labelText: 'PCS Heartbeat',
              helperText: '0 to 255',
              border: OutlineInputBorder(),
              isDense: true,
            ),
            keyboardType: const TextInputType.numberWithOptions(
              decimal: false,
              signed: false,
            ),
          ),
        ),
        SizedBox(
          width: 140,
          height: 44,
          child: FilledButton.tonal(
            onPressed: () {
              final value = int.tryParse(_heartbeatController.text.trim());
              if (value == null || value < 0 || value > 255) {
                _showMessage('Invalid heartbeat value. Use 0 to 255.');
                return;
              }
              _sendCommand(GatewayCommandNames.pcsHeartbeat, value: value);
            },
            child: const Text('Heartbeat'),
          ),
        ),
      ],
    );
  }

  Widget _buildPowerCommands() {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: [
        SizedBox(
          width: 120,
          height: 44,
          child: FilledButton(
            onPressed: () => _confirmAndSend(
              title: 'Confirm PCS Power ON',
              message: 'Are you sure you want to send PCS_POWER_ON?',
              command: GatewayCommandNames.pcsPowerOn,
            ),
            child: const Text('PCS ON'),
          ),
        ),
        SizedBox(
          width: 120,
          height: 44,
          child: FilledButton.tonal(
            onPressed: () => _confirmAndSend(
              title: 'Confirm PCS Power OFF',
              message: 'Recommended shutdown: set active/reactive power to 0 first, then send PCS_POWER_OFF. Continue?',
              command: GatewayCommandNames.pcsPowerOff,
            ),
            child: const Text('PCS OFF'),
          ),
        ),
        SizedBox(
          width: 130,
          height: 44,
          child: FilledButton.tonal(
            onPressed: () => _confirmAndSend(
              title: 'Confirm PCS Fault Reset',
              message: 'Send PCS_RESET_FAULT? Use only after checking actual PCS fault reason.',
              command: GatewayCommandNames.pcsResetFault,
            ),
            child: const Text('Reset Fault'),
          ),
        ),
      ],
    );
  }

  Future<void> _confirmAndSend({
    required String title,
    required String message,
    required String command,
  }) async {
    final confirmed = await _confirm(title: title, message: message);
    if (confirmed) {
      await _sendCommand(command);
    }
  }

  Future<void> _confirmAndSendValue({
    required String title,
    required String message,
    required String command,
    required dynamic value,
  }) async {
    final confirmed = await _confirm(title: title, message: message);
    if (confirmed) {
      await _sendCommand(command, value: value);
    }
  }

  Future<bool> _confirm({required String title, required String message}) async {
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

    return confirmed == true;
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }
}
