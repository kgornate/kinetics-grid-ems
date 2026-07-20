import 'package:flutter/material.dart';

import '../../../core/config/app_connection_config.dart';
import 'login_screen.dart';

class EnvironmentSelectScreen extends StatefulWidget {
  const EnvironmentSelectScreen({super.key});

  @override
  State<EnvironmentSelectScreen> createState() =>
      _EnvironmentSelectScreenState();
}

class _EnvironmentSelectScreenState extends State<EnvironmentSelectScreen> {
  ConnectionMode _mode = ConnectionMode.cloudflare;
  final _customUrlController = TextEditingController();

  @override
  void dispose() {
    _customUrlController.dispose();
    super.dispose();
  }

  AppConnectionConfig get _selectedConfig {
    switch (_mode) {
      case ConnectionMode.cloudflare:
        return AppConnectionConfig.cloudflare;
      case ConnectionMode.localEth0:
        return AppConnectionConfig.localEth0;
      case ConnectionMode.custom:
        return AppConnectionConfig.custom(_customUrlController.text);
    }
  }

  void _continue() {
    final config = _selectedConfig;
    if (config.baseUrl.trim().isEmpty) return;

    Navigator.of(context).pushReplacement(
      MaterialPageRoute(
        builder: (_) => LoginScreen(connection: config),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Select Connection')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560),
          child: Card(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    'Choose how the dashboard should connect to the gateway.',
                    style: theme.textTheme.bodyLarge,
                  ),
                  const SizedBox(height: 20),
                  RadioListTile<ConnectionMode>(
                    value: ConnectionMode.cloudflare,
                    groupValue: _mode,
                    title: const Text('Cloudflare'),
                    subtitle: const Text('https://ems-api.unityess.cloud'),
                    onChanged: (value) => setState(() => _mode = value!),
                  ),
                  RadioListTile<ConnectionMode>(
                    value: ConnectionMode.localEth0,
                    groupValue: _mode,
                    title: const Text('Local eth0'),
                    subtitle: const Text('http://192.168.10.2:8000'),
                    onChanged: (value) => setState(() => _mode = value!),
                  ),
                  RadioListTile<ConnectionMode>(
                    value: ConnectionMode.custom,
                    groupValue: _mode,
                    title: const Text('Custom URL'),
                    subtitle: const Text('Manually enter a base URL'),
                    onChanged: (value) => setState(() => _mode = value!),
                  ),
                  if (_mode == ConnectionMode.custom) ...[
                    const SizedBox(height: 12),
                    TextField(
                      controller: _customUrlController,
                      decoration: const InputDecoration(
                        labelText: 'Custom Base URL',
                        hintText: 'http://192.168.x.x:8000',
                        border: OutlineInputBorder(),
                      ),
                    ),
                  ],
                  const SizedBox(height: 20),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton(
                      onPressed: _continue,
                      child: const Text('Continue'),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
