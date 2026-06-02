import 'package:flutter/material.dart';

class CommandPanel extends StatefulWidget {
  final Future<void> Function(String command, {dynamic value}) onSendCommand;

  const CommandPanel({
    super.key,
    required this.onSendCommand,
  });

  @override
  State<CommandPanel> createState() => _CommandPanelState();
}

class _CommandPanelState extends State<CommandPanel> {
  final TextEditingController _temperatureController =
      TextEditingController(text: '25.0');

  final TextEditingController _pcsActivePowerController =
      TextEditingController(text: '20');

  final TextEditingController _pcsReactivePowerController =
      TextEditingController(text: '0');

  final TextEditingController _pcsHeartbeatController =
      TextEditingController(text: '1');

  String _selectedMode = '1';

  @override
  void dispose() {
    _temperatureController.dispose();
    _pcsActivePowerController.dispose();
    _pcsReactivePowerController.dispose();
    _pcsHeartbeatController.dispose();
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
              'Command Panel',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 16),

            _sectionTitle(context, 'Chiller Commands'),
            const SizedBox(height: 12),
            _buildChillerReadCommands(),

            const SizedBox(height: 18),
            _buildTemperatureCommand(),

            const SizedBox(height: 16),
            _buildModeCommand(),

            const SizedBox(height: 18),
            _buildChillerPowerCommands(),

            const SizedBox(height: 22),
            const Divider(),
            const SizedBox(height: 14),

            _sectionTitle(context, 'PCS / Inverter Commands'),
            const SizedBox(height: 12),
            _buildPcsReadCommands(),

            const SizedBox(height: 18),
            _buildPcsActivePowerCommand(),

            const SizedBox(height: 16),
            _buildPcsReactivePowerCommand(),

            const SizedBox(height: 16),
            _buildPcsHeartbeatCommand(),

            const SizedBox(height: 18),
            _buildPcsPowerCommands(),

            const SizedBox(height: 22),
            const Divider(),
            const SizedBox(height: 14),

            _sectionTitle(context, 'BMS / BCU Commands'),
            const SizedBox(height: 12),
            _buildBmsReadCommands(),

            const SizedBox(height: 18),
            _buildBmsControlCommands(),
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

  Widget _buildChillerReadCommands() {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: [
        FilledButton(
          onPressed: () => _sendCommand('READ_ALL'),
          child: const Text('Read Chiller'),
        ),
        FilledButton.tonal(
          onPressed: () => _sendCommand('READ_SETTINGS'),
          child: const Text('Read Settings'),
        ),
        FilledButton.tonal(
          onPressed: () => _sendCommand('READ_MODE'),
          child: const Text('Read Mode'),
        ),
        FilledButton.tonal(
          onPressed: () => _sendCommand('READ_TEMP'),
          child: const Text('Read Temp'),
        ),
        FilledButton.tonal(
          onPressed: () => _sendCommand('READ_ONOFF'),
          child: const Text('Read ON/OFF'),
        ),
      ],
    );
  }

  Widget _buildTemperatureCommand() {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        SizedBox(
          width: 230,
          child: TextField(
            controller: _temperatureController,
            decoration: const InputDecoration(
              labelText: 'Set Chiller Temperature',
              suffixText: '°C',
              border: OutlineInputBorder(),
              isDense: true,
            ),
            keyboardType: const TextInputType.numberWithOptions(
              decimal: true,
              signed: false,
            ),
          ),
        ),
        SizedBox(
          width: 120,
          height: 44,
          child: FilledButton(
            onPressed: () {
              final temp = double.tryParse(_temperatureController.text.trim());

              if (temp == null) {
                _showMessage('Invalid temperature value');
                return;
              }

              _sendCommand('SET_TEMP', value: temp);
            },
            child: const Text('Set Temp'),
          ),
        ),
      ],
    );
  }

  Widget _buildModeCommand() {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        SizedBox(
          width: 230,
          child: DropdownButtonFormField<String>(
            initialValue: _selectedMode,
            isExpanded: true,
            decoration: const InputDecoration(
              labelText: 'Chiller Control Mode',
              border: OutlineInputBorder(),
              isDense: true,
            ),
            items: const [
              DropdownMenuItem(
                value: '0',
                child: Text('Automatic', overflow: TextOverflow.ellipsis),
              ),
              DropdownMenuItem(
                value: '1',
                child: Text('Cooling / Refrigeration', overflow: TextOverflow.ellipsis),
              ),
              DropdownMenuItem(
                value: '2',
                child: Text('Heating', overflow: TextOverflow.ellipsis),
              ),
              DropdownMenuItem(
                value: '3',
                child: Text('Water Pump Circulation', overflow: TextOverflow.ellipsis),
              ),
            ],
            onChanged: (value) {
              if (value == null) return;
              setState(() {
                _selectedMode = value;
              });
            },
          ),
        ),
        SizedBox(
          width: 120,
          height: 44,
          child: FilledButton(
            onPressed: () {
              _sendCommand('SET_MODE', value: _selectedMode);
            },
            child: const Text('Set Mode'),
          ),
        ),
      ],
    );
  }

  Widget _buildChillerPowerCommands() {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: [
        SizedBox(
          width: 120,
          height: 44,
          child: FilledButton(
            onPressed: () => _confirmAndSend(
              title: 'Confirm Chiller ON',
              message: 'Are you sure you want to send CHILLER_ON command?',
              command: 'CHILLER_ON',
            ),
            child: const Text('Chiller ON'),
          ),
        ),
        SizedBox(
          width: 120,
          height: 44,
          child: FilledButton.tonal(
            onPressed: () => _confirmAndSend(
              title: 'Confirm Chiller OFF',
              message: 'Are you sure you want to send CHILLER_OFF command?',
              command: 'CHILLER_OFF',
            ),
            child: const Text('Chiller OFF'),
          ),
        ),
      ],
    );
  }

  Widget _buildPcsReadCommands() {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: [
        FilledButton(
          onPressed: () => _sendCommand('PCS_READ'),
          child: const Text('Read PCS'),
        ),
        FilledButton.tonal(
          onPressed: () => _sendCommand('STATUS'),
          child: const Text('Gateway Status'),
        ),
        FilledButton.tonal(
          onPressed: () => _sendCommand('READ_ALL_ASSETS'),
          child: const Text('Read All Assets'),
        ),
      ],
    );
  }

  Widget _buildPcsActivePowerCommand() {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        SizedBox(
          width: 230,
          child: TextField(
            controller: _pcsActivePowerController,
            decoration: const InputDecoration(
              labelText: 'PCS Active Power',
              suffixText: 'kW',
              helperText: '+ve discharge, -ve charge',
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
              final kw = double.tryParse(_pcsActivePowerController.text.trim());

              if (kw == null) {
                _showMessage('Invalid active power value');
                return;
              }

              _sendCommand('PCS_SET_ACTIVE_POWER', value: kw);
            },
            child: const Text('Set kW'),
          ),
        ),
      ],
    );
  }

  Widget _buildPcsReactivePowerCommand() {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        SizedBox(
          width: 230,
          child: TextField(
            controller: _pcsReactivePowerController,
            decoration: const InputDecoration(
              labelText: 'PCS Reactive Power',
              suffixText: 'kvar',
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
              final kvar = double.tryParse(_pcsReactivePowerController.text.trim());

              if (kvar == null) {
                _showMessage('Invalid reactive power value');
                return;
              }

              _sendCommand('PCS_SET_REACTIVE_POWER', value: kvar);
            },
            child: const Text('Set kvar'),
          ),
        ),
      ],
    );
  }

  Widget _buildPcsHeartbeatCommand() {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        SizedBox(
          width: 230,
          child: TextField(
            controller: _pcsHeartbeatController,
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
              final value = int.tryParse(_pcsHeartbeatController.text.trim());

              if (value == null) {
                _showMessage('Invalid heartbeat value');
                return;
              }

              _sendCommand('PCS_HEARTBEAT', value: value);
            },
            child: const Text('Heartbeat'),
          ),
        ),
      ],
    );
  }

  Widget _buildPcsPowerCommands() {
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
              message: 'Are you sure you want to send PCS_POWER_ON command?',
              command: 'PCS_POWER_ON',
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
              message: 'Are you sure you want to send PCS_POWER_OFF command?',
              command: 'PCS_POWER_OFF',
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
              message: 'Are you sure you want to send PCS_RESET_FAULT command?',
              command: 'PCS_RESET_FAULT',
            ),
            child: const Text('Reset Fault'),
          ),
        ),
      ],
    );
  }


  Widget _buildBmsReadCommands() {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: [
        FilledButton(
          onPressed: () => _sendCommand('READ_BMS_ALL'),
          child: const Text('Read BMS'),
        ),
        FilledButton.tonal(
          onPressed: () => _sendCommand('READ_BMS_ALARMS'),
          child: const Text('Read BMS Alarms'),
        ),
        FilledButton.tonal(
          onPressed: () => _sendCommand('READ_ALL_ASSETS'),
          child: const Text('Read All Assets'),
        ),
      ],
    );
  }

  Widget _buildBmsControlCommands() {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: [
        SizedBox(
          width: 150,
          height: 44,
          child: FilledButton(
            onPressed: () => _confirmAndSend(
              title: 'Confirm BMS Precharge Start',
              message: 'Are you sure you want to send START_BMS_PRECHARGE command?',
              command: 'START_BMS_PRECHARGE',
            ),
            child: const Text('Start Precharge'),
          ),
        ),
        SizedBox(
          width: 150,
          height: 44,
          child: FilledButton.tonal(
            onPressed: () => _confirmAndSend(
              title: 'Confirm BMS Precharge Stop',
              message: 'Are you sure you want to send STOP_BMS_PRECHARGE command?',
              command: 'STOP_BMS_PRECHARGE',
            ),
            child: const Text('Stop Precharge'),
          ),
        ),
        SizedBox(
          width: 170,
          height: 44,
          child: FilledButton.tonal(
            onPressed: () => _confirmAndSend(
              title: 'Confirm Insulation Test',
              message: 'Are you sure you want to send START_BMS_INSULATION_TEST command?',
              command: 'START_BMS_INSULATION_TEST',
            ),
            child: const Text('Insulation Test'),
          ),
        ),
        SizedBox(
          width: 110,
          height: 44,
          child: FilledButton.tonal(
            onPressed: () => _sendCommand('BMS_FAN_AUTO'),
            child: const Text('Fan Auto'),
          ),
        ),
        SizedBox(
          width: 100,
          height: 44,
          child: FilledButton.tonal(
            onPressed: () => _sendCommand('BMS_FAN_ON'),
            child: const Text('Fan ON'),
          ),
        ),
        SizedBox(
          width: 100,
          height: 44,
          child: FilledButton.tonal(
            onPressed: () => _sendCommand('BMS_FAN_OFF'),
            child: const Text('Fan OFF'),
          ),
        ),
        SizedBox(
          width: 120,
          height: 44,
          child: FilledButton.tonal(
            onPressed: () => _confirmAndSend(
              title: 'Confirm BCU Reset',
              message: 'Are you sure you want to send RESET_BCU command?',
              command: 'RESET_BCU',
            ),
            child: const Text('Reset BCU'),
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
      await _sendCommand(command);
    }
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
      ),
    );
  }
}
