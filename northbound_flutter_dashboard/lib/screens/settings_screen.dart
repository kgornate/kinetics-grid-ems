import 'package:flutter/material.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({
    super.key,
    required this.apiBaseUrl,
    required this.wsUrl,
    required this.onApply,
  });

  final String apiBaseUrl;
  final String wsUrl;
  final void Function(String apiBaseUrl, String wsUrl) onApply;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late final TextEditingController apiController;
  late final TextEditingController wsController;

  @override
  void initState() {
    super.initState();
    apiController = TextEditingController(text: widget.apiBaseUrl);
    wsController = TextEditingController(text: widget.wsUrl);
  }

  @override
  void dispose() {
    apiController.dispose();
    wsController.dispose();
    super.dispose();
  }

  void useLocal() {
    apiController.text = 'http://192.168.10.2:8000';
    wsController.text = 'ws://192.168.10.2:8000/ws/telemetry';
  }

  void useCloudflare() {
    apiController.text = 'https://ems-api.unityess.cloud';
    wsController.text = 'wss://ems-api.unityess.cloud/ws/telemetry';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Connection Settings')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
            controller: apiController,
            decoration: const InputDecoration(
              labelText: 'API base URL',
              helperText: 'Local eth0 default: http://192.168.10.2:8000',
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: wsController,
            decoration: const InputDecoration(
              labelText: 'WebSocket URL',
              helperText: 'Local eth0 default: ws://192.168.10.2:8000/ws/telemetry',
            ),
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 8,
            children: [
              OutlinedButton(onPressed: useLocal, child: const Text('Use local eth0')),
              OutlinedButton(onPressed: useCloudflare, child: const Text('Use Cloudflare')),
              FilledButton(
                onPressed: () {
                  widget.onApply(apiController.text.trim(), wsController.text.trim());
                  Navigator.of(context).pop();
                },
                child: const Text('Apply'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
