import 'package:flutter/material.dart';

class GatewayConfigCard extends StatelessWidget {
  const GatewayConfigCard({
    super.key,
    required this.gatewayIpController,
    required this.udpRunning,
    required this.commandInProgress,
    required this.onToggleUdp,
    required this.onOpenLogs,
  });

  final TextEditingController gatewayIpController;
  final bool udpRunning;
  final bool commandInProgress;
  final VoidCallback onToggleUdp;
  final VoidCallback onOpenLogs;

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 1,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: gatewayIpController,
                decoration: const InputDecoration(
                  labelText: 'i.MX93 Gateway IP',
                  border: OutlineInputBorder(),
                  prefixIcon: Icon(Icons.router),
                ),
              ),
            ),
            const SizedBox(width: 12),
            FilledButton.tonal(
              onPressed: onToggleUdp,
              child: Text(udpRunning ? 'Stop UDP' : 'Start UDP'),
            ),
            const SizedBox(width: 12),
            FilledButton.icon(
              onPressed: onOpenLogs,
              icon: const Icon(Icons.history),
              label: const Text('Logs'),
            ),
            const SizedBox(width: 12),
            if (commandInProgress)
              const SizedBox(
                width: 28,
                height: 28,
                child: CircularProgressIndicator(strokeWidth: 3),
              ),
          ],
        ),
      ),
    );
  }
}
