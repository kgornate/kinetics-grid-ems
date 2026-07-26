import 'package:flutter/material.dart';

import '../core/state/gateway_controller.dart';
import '../models/gateway_models.dart';
import '../widgets/common_widgets.dart';

class AlarmsScreen extends StatefulWidget {
  const AlarmsScreen({super.key, required this.controller});

  final GatewayController controller;

  @override
  State<AlarmsScreen> createState() => _AlarmsScreenState();
}

class _AlarmsScreenState extends State<AlarmsScreen> {
  bool _historyMode = false;
  bool _loading = false;
  List<Map<String, dynamic>> _history = <Map<String, dynamic>>[];

  Future<void> _loadHistory() async {
    setState(() => _loading = true);
    try {
      _history = await widget.controller.loadAlarmHistory();
      _historyMode = true;
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final alarms = _historyMode ? _history : widget.controller.activeAlarms;
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        children: [
          SectionHeader(
            _historyMode ? 'Alarm history' : 'Active alarms',
            subtitle: '${alarms.length} records',
            trailing: Wrap(
              spacing: 8,
              children: [
                if (_historyMode)
                  OutlinedButton.icon(
                    onPressed: () => setState(() => _historyMode = false),
                    icon: const Icon(Icons.notifications_active),
                    label: const Text('Active'),
                  )
                else
                  OutlinedButton.icon(
                    onPressed: _loading ? null : _loadHistory,
                    icon: const Icon(Icons.history),
                    label: const Text('History'),
                  ),
                FilledButton.tonalIcon(
                  onPressed: () => widget.controller.refreshAlarms(),
                  icon: const Icon(Icons.refresh),
                  label: const Text('Refresh'),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : alarms.isEmpty
                    ? const Center(child: Text('No alarms found.'))
                    : Card(
                        child: ListView.separated(
                          itemCount: alarms.length,
                          separatorBuilder: (_, __) => const Divider(height: 1),
                          itemBuilder: (context, index) {
                            final alarm = alarms[index];
                            final severity = (alarm['severity'] ?? 'unknown').toString();
                            return ListTile(
                              leading: Icon(
                                severity.toLowerCase().contains('critical') || severity.toLowerCase().contains('level1')
                                    ? Icons.dangerous
                                    : Icons.warning_amber,
                                color: Theme.of(context).colorScheme.error,
                              ),
                              title: Text((alarm['message'] ?? alarm['alarm_key'] ?? 'Alarm').toString()),
                              subtitle: Text(
                                '${prettifyKey((alarm['asset_id'] ?? 'unknown').toString())} | $severity | ${alarm['raised_at'] ?? alarm['timestamp'] ?? '--'}',
                              ),
                              trailing: alarm['active'] == false
                                  ? const Chip(label: Text('Cleared'))
                                  : const Chip(label: Text('Active')),
                            );
                          },
                        ),
                      ),
          ),
        ],
      ),
    );
  }
}
