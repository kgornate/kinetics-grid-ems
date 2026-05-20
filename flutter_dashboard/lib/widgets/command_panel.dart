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

  String _selectedMode = '1';

  @override
  void dispose() {
    _temperatureController.dispose();
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
        child: LayoutBuilder(
          builder: (context, constraints) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Command Panel',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 16),

                _buildReadCommands(),

                const SizedBox(height: 20),
                const Divider(),
                const SizedBox(height: 12),

                _buildTemperatureCommand(),

                const SizedBox(height: 16),

                _buildModeCommand(),

                const SizedBox(height: 20),
                const Divider(),
                const SizedBox(height: 12),

                _buildPowerCommands(),
              ],
            );
          },
        ),
      ),
    );
  }

  Widget _buildReadCommands() {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: [
        FilledButton(
          onPressed: () => _sendCommand('READ_ALL'),
          child: const Text('Read All'),
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
              labelText: 'Set Temperature',
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
              labelText: 'Control Mode',
              border: OutlineInputBorder(),
              isDense: true,
            ),
            items: const [
              DropdownMenuItem(
                value: '0',
                child: Text(
                  'Automatic',
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              DropdownMenuItem(
                value: '1',
                child: Text(
                  'Cooling / Refrigeration',
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              DropdownMenuItem(
                value: '2',
                child: Text(
                  'Heating',
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              DropdownMenuItem(
                value: '3',
                child: Text(
                  'Water Pump Circulation',
                  overflow: TextOverflow.ellipsis,
                ),
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