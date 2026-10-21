import 'dart:async';
import 'package:flutter/material.dart';
import '../core/state/gateway_controller.dart';
import '../widgets/common_widgets.dart';
import 'kalpa_monitoring_screen.dart';

class MeterScreen extends StatefulWidget {
  const MeterScreen({super.key, required this.controller, this.active = true});
  final GatewayController controller;
  final bool active;
  @override
  State<MeterScreen> createState() => _MeterScreenState();
}

class _MeterScreenState extends State<MeterScreen> {
  Timer? timer;
  List<Map<String, dynamic>> history = [];
  bool loading = false;
  String? historyError;
  @override
  void initState() {
    super.initState();
    if (widget.active) unawaited(_history());
    timer = Timer.periodic(const Duration(seconds: 15), (_) {
      if (widget.active) unawaited(_history());
    });
  }

  @override
  void didUpdateWidget(covariant MeterScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.active && !oldWidget.active) unawaited(_history());
  }

  @override
  void dispose() {
    timer?.cancel();
    super.dispose();
  }

  Future<void> _history() async {
    if (loading) return;
    setState(() => loading = true);
    try {
      final result = await widget.controller.loadHistorian(
        'acrel_meter_1',
        limit: 60,
      );
      if (mounted)
        setState(() {
          history = result;
          historyError = null;
        });
    } catch (error) {
      if (mounted) setState(() => historyError = error.toString());
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  String _point(
    Map<String, dynamic>? asset,
    String key,
    String unit, {
    bool historical = false,
  }) {
    final point = kalpaMap(kalpaMap(asset?['telemetry'])[key]);
    final quality = point['quality'] ?? point['q'];
    if (asset?['online'] != true ||
        (!historical && !widget.controller.meterLive) ||
        !['good', 'mock'].contains(quality))
      return '—';
    return kalpaNumber(point['value'] ?? point['v'], unit, 2);
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
    animation: widget.controller,
    builder: (context, _) {
      final c = widget.controller, meter = c.meter;
      final status = c.meterError != null
          ? 'API unavailable'
          : !c.meterLive && meter?['online'] == true
          ? 'Stale'
          : meter?['status']?.toString() ?? 'Not enabled';
      final source = meter?['source']?.toString() ?? 'Unknown';
      final notice =
          c.meterError ??
          (meter == null
              ? 'Meter is not enabled on this gateway.'
              : !c.meterLive
              ? 'Live meter readings are unavailable. Check power and RS485.'
              : meter['scaling_validated'] != true
              ? 'Measurement scaling and direction await physical commissioning.'
              : '');
      Widget metric(String title, String key, String unit) =>
          MetricTile(label: title, value: _point(meter, key, unit));
      return ListView(
        padding: const EdgeInsets.all(20),
        children: [
          SectionHeader(
            'ACREL APM520',
            subtitle:
                '${meter?['location'] ?? 'Unassigned location'} · Source: $source',
            trailing: StatusPill(
              label: status,
              good: c.meterLive && status == 'online',
            ),
          ),
          if (source == 'mock')
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 12),
              child: Text(
                'SIMULATED METER DATA — not physical measurements',
                style: TextStyle(fontWeight: FontWeight.bold),
              ),
            ),
          if (notice.isNotEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 12),
              child: Text(notice),
            ),
          MetricGrid(
            children: [
              metric('Active power', 'active_power_total_kw', 'kW'),
              metric('Reactive power', 'reactive_power_total_kvar', 'kvar'),
              metric('Apparent power', 'apparent_power_total_kva', 'kVA'),
              metric('Neutral current', 'current_neutral_a', 'A'),
              metric('Power factor', 'power_factor_total', ''),
              metric('Frequency', 'frequency_hz', 'Hz'),
            ],
          ),
          const SizedBox(height: 20),
          const Text(
            'Three-phase measurements',
            style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
          ),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: DataTable(
              columns: const [
                DataColumn(label: Text('Phase')),
                DataColumn(label: Text('L–N voltage')),
                DataColumn(label: Text('Line voltage')),
                DataColumn(label: Text('Current')),
                DataColumn(label: Text('Active power')),
                DataColumn(label: Text('Reactive power')),
                DataColumn(label: Text('Apparent power')),
                DataColumn(label: Text('PF')),
              ],
              rows: ['a', 'b', 'c'].asMap().entries.map((entry) {
                final p = entry.value;
                return DataRow(
                  cells: [
                    DataCell(Text(p.toUpperCase())),
                    DataCell(Text(_point(meter, 'voltage_${p}_v', 'V'))),
                    DataCell(
                      Text(
                        _point(
                          meter,
                          'voltage_${['ab', 'bc', 'ca'][entry.key]}_v',
                          'V',
                        ),
                      ),
                    ),
                    DataCell(Text(_point(meter, 'current_${p}_a', 'A'))),
                    DataCell(Text(_point(meter, 'active_power_${p}_kw', 'kW'))),
                    DataCell(
                      Text(_point(meter, 'reactive_power_${p}_kvar', 'kvar')),
                    ),
                    DataCell(
                      Text(_point(meter, 'apparent_power_${p}_kva', 'kVA')),
                    ),
                    DataCell(Text(_point(meter, 'power_factor_$p', ''))),
                  ],
                );
              }).toList(),
            ),
          ),
          const SizedBox(height: 20),
          const Text(
            'Primary-side energy counters',
            style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
          ),
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 10),
            child: Text(
              'Forward/reverse follow meter direction. Import/export labels are not assigned until commissioning.',
            ),
          ),
          MetricGrid(
            children: [
              metric('Total active energy', 'active_energy_total_kwh', 'kWh'),
              metric(
                'Forward active energy',
                'active_energy_forward_kwh',
                'kWh',
              ),
              metric(
                'Reverse active energy',
                'active_energy_reverse_kwh',
                'kWh',
              ),
              metric(
                'Total reactive energy',
                'reactive_energy_total_kvarh',
                'kvarh',
              ),
              metric(
                'Forward reactive energy',
                'reactive_energy_forward_kvarh',
                'kvarh',
              ),
              metric(
                'Reverse reactive energy',
                'reactive_energy_reverse_kvarh',
                'kvarh',
              ),
              metric('Apparent energy', 'apparent_energy_total_kvah', 'kVAh'),
            ],
          ),
          const SizedBox(height: 18),
          Text('Last measurement: ${kalpaTime(meter?['timestamp'])}'),
          Text('Last attempt: ${kalpaTime(meter?['last_attempt_at'])}'),
          if (meter?['read_errors'] is List)
            ...(meter!['read_errors'] as List).map(
              (error) => Text(
                '${kalpaMap(error)['block']}: ${kalpaMap(error)['error']}',
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
          const SizedBox(height: 20),
          SectionHeader(
            'Recent history',
            subtitle: 'Latest 60 stored samples · newest first · not live data',
            trailing: TextButton.icon(
              onPressed: loading ? null : _history,
              icon: const Icon(Icons.refresh),
              label: Text(loading ? 'Loading…' : 'Refresh history'),
            ),
          ),
          if (historyError != null) Text('History unavailable: $historyError'),
          if (history.isEmpty && !loading)
            const Padding(
              padding: EdgeInsets.all(12),
              child: Text(
                'No stored samples yet. History follows the gateway storage interval.',
              ),
            ),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: DataTable(
              columns: const [
                DataColumn(label: Text('Stored at')),
                DataColumn(label: Text('Status')),
                DataColumn(label: Text('Source')),
                DataColumn(label: Text('Active power')),
                DataColumn(label: Text('Forward kWh')),
                DataColumn(label: Text('Reverse kWh')),
              ],
              rows: history.map((row) {
                final a = kalpaMap(row['payload']);
                return DataRow(
                  cells: [
                    DataCell(Text(kalpaTime(row['timestamp']))),
                    DataCell(Text('${a['status'] ?? 'Unknown'}')),
                    DataCell(Text('${a['source'] ?? 'Unknown'}')),
                    DataCell(
                      Text(
                        _point(
                          a,
                          'active_power_total_kw',
                          'kW',
                          historical: true,
                        ),
                      ),
                    ),
                    DataCell(
                      Text(
                        _point(
                          a,
                          'active_energy_forward_kwh',
                          '',
                          historical: true,
                        ),
                      ),
                    ),
                    DataCell(
                      Text(
                        _point(
                          a,
                          'active_energy_reverse_kwh',
                          '',
                          historical: true,
                        ),
                      ),
                    ),
                  ],
                );
              }).toList(),
            ),
          ),
        ],
      );
    },
  );
}
