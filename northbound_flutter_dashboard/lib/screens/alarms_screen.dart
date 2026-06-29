import 'package:flutter/material.dart';

import '../api/northbound_api_client.dart';
import '../models/alarm_record.dart';

class AlarmsScreen extends StatefulWidget {
  const AlarmsScreen({super.key, required this.apiClient});

  final NorthboundApiClient apiClient;

  @override
  State<AlarmsScreen> createState() => _AlarmsScreenState();
}

class _AlarmsScreenState extends State<AlarmsScreen> {
  List<AlarmRecord> alarms = [];
  String? error;
  bool loading = false;

  @override
  void initState() {
    super.initState();
    refresh();
  }

  Future<void> refresh() async {
    setState(() {
      loading = true;
      error = null;
    });
    final result = await widget.apiClient.getAlarms();
    if (!mounted) return;
    setState(() {
      loading = false;
      if (result.isSuccess) {
        alarms = result.data ?? [];
      } else {
        error = result.error;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Alarms'), actions: [IconButton(onPressed: refresh, icon: const Icon(Icons.refresh))]),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (loading) const LinearProgressIndicator(),
          if (error != null) Card(child: ListTile(leading: const Icon(Icons.error), title: Text(error!))),
          if (alarms.isEmpty) const Card(child: ListTile(leading: Icon(Icons.check_circle), title: Text('No active alarms'))),
          for (final alarm in alarms)
            Card(
              child: ListTile(
                leading: const Icon(Icons.warning),
                title: Text('${alarm.severity.toUpperCase()} • ${alarm.assetId}'),
                subtitle: Text('${alarm.message}\n${alarm.timestampUtc}'),
                isThreeLine: true,
              ),
            ),
        ],
      ),
    );
  }
}
