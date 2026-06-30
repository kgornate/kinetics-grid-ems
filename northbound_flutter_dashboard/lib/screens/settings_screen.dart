import 'package:flutter/material.dart';

import '../config/app_config.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({
    super.key,
    required this.activeProfile,
    required this.onApply,
  });

  final ApiProfile activeProfile;
  final void Function(ApiProfile profile) onApply;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late final TextEditingController nameController;
  late final TextEditingController restController;
  late final TextEditingController wsController;
  late final TextEditingController logsController;
  late final TextEditingController timeoutController;

  @override
  void initState() {
    super.initState();
    nameController = TextEditingController(text: widget.activeProfile.name);
    restController = TextEditingController(text: widget.activeProfile.restBaseUrl);
    wsController = TextEditingController(text: widget.activeProfile.wsUrl);
    logsController = TextEditingController(text: widget.activeProfile.logsBaseUrl);
    timeoutController = TextEditingController(text: widget.activeProfile.httpTimeout.inSeconds.toString());
  }

  @override
  void dispose() {
    nameController.dispose();
    restController.dispose();
    wsController.dispose();
    logsController.dispose();
    timeoutController.dispose();
    super.dispose();
  }

  void useLocal() => _loadProfile(ApiProfile.localEth0);

  void useCloudflare() => _loadProfile(ApiProfile.cloudflare);

  void _loadProfile(ApiProfile profile) {
    nameController.text = profile.name;
    restController.text = profile.restBaseUrl;
    wsController.text = profile.wsUrl;
    logsController.text = profile.logsBaseUrl;
    timeoutController.text = profile.httpTimeout.inSeconds.toString();
  }

  void _apply() {
    final restUrl = restController.text.trim();
    final timeoutSec = int.tryParse(timeoutController.text.trim()) ?? ApiProfile.recommendedTimeoutFor(restUrl).inSeconds;
    final profile = ApiProfile(
      name: nameController.text.trim().isEmpty ? 'Custom' : nameController.text.trim(),
      restBaseUrl: restUrl,
      wsUrl: wsController.text.trim(),
      logsBaseUrl: logsController.text.trim().isEmpty ? restUrl : logsController.text.trim(),
      httpTimeout: Duration(seconds: timeoutSec.clamp(1, 120).toInt()),
    );
    widget.onApply(profile);
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Connection Settings')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              OutlinedButton(onPressed: useLocal, child: const Text('Use local eth0')),
              OutlinedButton(onPressed: useCloudflare, child: const Text('Use Cloudflare')),
              FilledButton(onPressed: _apply, child: const Text('Apply')),
            ],
          ),
          const SizedBox(height: 18),
          TextField(
            controller: nameController,
            decoration: const InputDecoration(
              labelText: 'Profile name',
              helperText: 'Example: Local eth0 or Cloudflare',
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: restController,
            decoration: const InputDecoration(
              labelText: 'REST API base URL',
              helperText: 'Local: http://192.168.10.2:8000 | Cloudflare: https://ems-api.unityess.cloud',
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: wsController,
            decoration: const InputDecoration(
              labelText: 'WebSocket URL',
              helperText: 'Local uses ws://... and Cloudflare uses wss://...',
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: logsController,
            decoration: const InputDecoration(
              labelText: 'Logs API base URL',
              helperText: 'For NorthBound v0.5 keep same as REST API unless a separate logs route is deployed.',
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: timeoutController,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(
              labelText: 'HTTP timeout seconds',
              helperText: 'Recommended: 5 for local eth0, 30 for Cloudflare/hotspot/remote access.',
            ),
          ),
          const SizedBox(height: 18),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: const [
                  Text('Why timeout is profile-based', style: TextStyle(fontWeight: FontWeight.w700)),
                  SizedBox(height: 8),
                  Text('Local eth0 asset telemetry usually responds in a few seconds, so 5 seconds is enough.'),
                  Text('Cloudflare over hotspot/Wi-Fi can take 10–15 seconds for large BMS payloads, so 30 seconds is safer.'),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
