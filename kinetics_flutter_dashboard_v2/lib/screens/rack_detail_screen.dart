import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../core/presentation/telemetry_presentation.dart';
import '../core/state/gateway_controller.dart';
import '../models/gateway_models.dart';
import '../widgets/common_widgets.dart';

class RackDetailScreen extends StatefulWidget {
  const RackDetailScreen({
    super.key,
    required this.controller,
    required this.rack,
  });

  final GatewayController controller;
  final AssetSnapshot rack;

  @override
  State<RackDetailScreen> createState() => _RackDetailScreenState();
}

class _RackDetailScreenState extends State<RackDetailScreen> {
  late AssetSnapshot _rack = widget.rack;
  bool _loading = false;
  String? _loadError;

  bool get _hasCellData {
    final value = _rack.telemetry['vcell']?.value;
    return value is List && value.any((item) => item is num && item != 0);
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && !_hasCellData) {
        _loadDetails();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final rackId = _rack.rackId ?? 0;
    return DefaultTabController(
      length: 7,
      child: Scaffold(
        appBar: AppBar(
          title: Text('Rack $rackId / BCU $rackId'),
          bottom: const TabBar(
            isScrollable: true,
            tabs: [
              Tab(text: 'Overview'),
              Tab(text: 'Electrical'),
              Tab(text: 'Thermal'),
              Tab(text: 'Cells'),
              Tab(text: 'Sensors'),
              Tab(text: 'Alarms & faults'),
              Tab(text: 'All signals'),
            ],
          ),
          actions: [
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 10),
              child: StatusPill(label: _rack.online ? 'Online' : 'Offline', good: _rack.online),
            ),
            const SizedBox(width: 8),
            FilledButton.tonalIcon(
              onPressed: _loading ? null : _loadDetails,
              icon: _loading
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.download),
              label: const Text('Load complete rack data'),
            ),
            const SizedBox(width: 12),
          ],
        ),
        body: TabBarView(
          children: [
            _overview(),
            _electrical(),
            _thermal(),
            _cells(),
            _sensors(),
            _alarms(),
            ListView(padding: const EdgeInsets.all(20), children: [EngineeringTable(asset: _rack, maxHeight: 720)]),
          ],
        ),
      ),
    );
  }

  Future<void> _loadDetails() async {
    final rackId = _rack.rackId;
    if (rackId == null || _loading) return;
    setState(() {
      _loading = true;
      _loadError = null;
    });
    try {
      final result = await widget.controller.loadRackDetails(rackId);
      if (mounted) {
        setState(() {
          _rack = result;
          _loadError = null;
        });
      }
    } catch (error) {
      if (mounted) setState(() => _loadError = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Widget _overview() {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        SectionHeader(
          'Rack ${_rack.rackId} overview',
          subtitle: '${_rack.telemetry.length} mapped points • ${_rack.timestamp == null ? 'No timestamp' : shortTime(_rack.timestamp!)}',
        ),
        const SizedBox(height: 16),
        MetricGrid(
          children: [
            _metric('vrack', 'Rack voltage', Icons.bolt, emphasis: true),
            _metric('irack', 'Rack current', Icons.electric_meter, emphasis: true),
            _metric('soc', 'State of charge', Icons.battery_5_bar, emphasis: true),
            _metric('soh', 'State of health', Icons.favorite, emphasis: true),
            _metric('vcell_max', 'Maximum cell voltage', Icons.arrow_upward),
            _metric('vcell_min', 'Minimum cell voltage', Icons.arrow_downward),
            _metric('vcell_diff', 'Cell voltage spread', Icons.compare_arrows),
            _metric('tcell_max', 'Maximum cell temperature', Icons.thermostat),
            _metric('tcell_min', 'Minimum cell temperature', Icons.device_thermostat),
            _metric('max_bat_temp_diff', 'Temperature spread', Icons.device_thermostat),
            _metric('ir', 'Insulation resistance', Icons.shield_outlined),
            _metric('pdu_max_temp', 'Maximum PDU temperature', Icons.thermostat),
          ],
        ),
        const SizedBox(height: 20),
        TelemetrySection(
          title: 'Operating state',
          asset: _rack,
          entries: entriesForKeys(_rack, const [
            'bcu_run_state', 'current_state', 'pre_charge_state', 'pre_charge_fail_reason',
            'contactor_state', 'full_or_empty_flag', 'heart_beat_num',
          ]),
        ),
        TelemetrySection(
          title: 'Battery capability',
          asset: _rack,
          entries: entriesForKeys(_rack, const [
            'soc', 'rack_inner_soc', 'soh', 'irack_chg_limit', 'irack_dsg_limit',
            'today_echg_cum', 'today_edsg_cum', 'month_echg_curr', 'month_edsg_curr',
            'year_echg_cum', 'year_edsg_cum', 'total_echg_cum', 'total_edsg_cum',
          ]),
        ),
      ],
    );
  }

  Widget _electrical() {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        SectionHeader('Electrical and battery measurements', subtitle: 'Read-only live values and capability limits'),
        const SizedBox(height: 16),
        MetricGrid(children: [
          _metric('vrack', 'Rack voltage', Icons.bolt, emphasis: true),
          _metric('irack', 'Rack current', Icons.electric_meter, emphasis: true),
          _metric('bmu_total_vol', 'BMU accumulated voltage', Icons.account_tree),
          _metric('pre_charge_volt', 'Pre-charge voltage', Icons.flash_on),
          _metric('irack_chg_limit', 'Charge current limit', Icons.south),
          _metric('irack_dsg_limit', 'Discharge current limit', Icons.north),
          _metric('ir', 'Insulation resistance', Icons.shield),
          _metric('ir_pos', 'Positive insulation', Icons.add_circle_outline),
          _metric('ir_neg', 'Negative insulation', Icons.remove_circle_outline),
          _metric('supply_sample_vol', 'Controller supply voltage', Icons.power),
        ]),
        const SizedBox(height: 20),
        TelemetrySection(
          title: 'Electrical measurements',
          asset: _rack,
          entries: entriesForKeys(_rack, const [
            'vrack', 'irack', 'pre_charge_volt', 'bmu_total_vol', 'ncon_total_vol',
            'ir', 'ir_pos', 'ir_neg', 'supply_sample_vol', 'hvil_in_sample', 'clu_resistance',
          ]),
        ),
        TelemetrySection(
          title: 'Power-flow limits and capacity',
          asset: _rack,
          entries: entriesForKeys(_rack, const [
            'irack_chg_limit', 'irack_dsg_limit', 'soc', 'rack_inner_soc', 'soh',
            'today_echg_cum', 'today_edsg_cum', 'month_echg_curr', 'month_edsg_curr',
            'year_echg_cum', 'year_edsg_cum', 'total_echg_cum', 'total_edsg_cum',
          ]),
        ),
        TelemetrySection(
          title: 'Alarm and shutdown snapshots',
          subtitle: 'Values captured when a protection event occurred',
          asset: _rack,
          entries: entriesWhere(_rack, (key, point) {
            final lower = key.toLowerCase();
            return lower.startsWith('alarm_') || lower.startsWith('stop_') || lower.contains('_alm_') || lower.contains('_halt_');
          }),
          initiallyExpanded: false,
        ),
      ],
    );
  }

  Widget _thermal() {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        SectionHeader('Thermal condition', subtitle: 'Cell, terminal, PDU, busbar and coolant measurements'),
        const SizedBox(height: 16),
        MetricGrid(children: [
          _metric('tcell_max', 'Maximum cell temperature', Icons.thermostat, emphasis: true),
          _metric('tcell_min', 'Minimum cell temperature', Icons.device_thermostat, emphasis: true),
          _metric('tcell_avg', 'Average cell temperature', Icons.thermostat),
          _metric('max_bat_temp_diff', 'Cell temperature spread', Icons.compare_arrows),
          _metric('tterm_max', 'Maximum terminal temperature', Icons.thermostat),
          _metric('pdu_max_temp', 'Maximum PDU temperature', Icons.thermostat),
          _metric('tcopper_max', 'Maximum busbar temperature', Icons.thermostat),
          _metric('tcoolant_max', 'Maximum coolant temperature', Icons.water_drop),
        ]),
        const SizedBox(height: 20),
        TelemetrySection(
          title: 'Cell temperature summary',
          asset: _rack,
          entries: entriesForKeys(_rack, const [
            'tcell_max', 'tcell_max_num', 'tcell_max_pack', 'tcell_max_position',
            'tcell_min', 'tcell_min_num', 'tcell_min_pack', 'tcell_min_position',
            'tcell_avg', 'max_bat_temp_diff', 'max_bat_temp_rise',
          ]),
        ),
        TelemetrySection(
          title: 'PDU and terminal temperatures',
          asset: _rack,
          entries: entriesWhere(_rack, (key, point) {
            final lower = key.toLowerCase();
            return lower.contains('pdu_temp') || lower.contains('tterm');
          }),
        ),
        TelemetrySection(
          title: 'Busbar and coolant summary',
          asset: _rack,
          entries: entriesForKeys(_rack, const [
            'tcopper_max', 'pos_of_tcopper_max', 'tcoolant_max', 'pos_of_tcoolant_max',
          ]),
        ),
      ],
    );
  }

  Widget _cells() {
    final voltages = _numericList('vcell');
    final temperatures = _numericList('tcell');
    return CellChannelsView(
      rackId: _rack.rackId ?? 0,
      voltages: voltages,
      temperatures: temperatures,
      loading: _loading,
      error: _loadError,
      onReload: _loadDetails,
    );
  }

  Widget _sensors() {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        SectionHeader(
          'Rack sensor channels',
          subtitle: 'Temperature channels are separate BMS sensor arrays; zero-filled reserved channels are hidden.',
        ),
        const SizedBox(height: 16),
        SensorArraySection(title: 'Positive terminal temperatures', values: _numericList('tterm_pos'), unit: '°C'),
        SensorArraySection(title: 'Negative terminal temperatures', values: _numericList('tterm_neg'), unit: '°C'),
        SensorArraySection(title: 'Busbar temperatures', values: _numericList('copper_temp'), unit: '°C'),
        SensorArraySection(title: 'Coolant temperatures', values: _numericList('coolant_temp'), unit: '°C'),
      ],
    );
  }

  Widget _alarms() {
    final global = widget.controller.activeAlarms.where((alarm) {
      final assetId = alarm['asset_id']?.toString();
      return assetId == _rack.assetId || assetId == 'rack_${_rack.rackId}';
    }).toList();
    final signalEntries = entriesWhere(_rack, (key, point) {
      final lower = '${key}_${point.nameEn ?? ''}'.toLowerCase();
      return lower.contains('alarm') || lower.contains('fault') || lower.contains('warn');
    });
    final activeSignals = <Map<String, String>>[];
    for (final entry in signalEntries) {
      for (final bit in activeBits(entry.value)) {
        activeSignals.add(<String, String>{
          'source': friendlyName(entry.key, entry.value),
          'detail': prettifyKey(bit.key),
          'value': bit.value.toString(),
        });
      }
    }

    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        SectionHeader(
          'Rack alarms and faults',
          subtitle: '${global.length} gateway alarms • ${activeSignals.length} active decoded bits',
        ),
        const SizedBox(height: 16),
        if (global.isEmpty && activeSignals.isEmpty)
          const Card(child: ListTile(leading: Icon(Icons.check_circle), title: Text('No active rack alarm reported'))),
        ...global.map((alarm) => Card(
              child: ListTile(
                leading: const Icon(Icons.warning_amber),
                title: Text((alarm['message'] ?? alarm['alarm_key'] ?? 'Alarm').toString()),
                subtitle: Text('${alarm['severity'] ?? '--'} • ${alarm['timestamp'] ?? ''}'),
              ),
            )),
        ...activeSignals.map((alarm) => Card(
              child: ListTile(
                leading: const Icon(Icons.report_problem),
                title: Text(alarm['detail']!),
                subtitle: Text('Decoded from ${alarm['source']}'),
              ),
            )),
        const SizedBox(height: 16),
        TelemetrySection(
          title: 'All alarm and fault registers',
          asset: _rack,
          entries: signalEntries,
        ),
      ],
    );
  }

  Widget _metric(String key, String label, IconData icon, {bool emphasis = false}) {
    final point = _rack.telemetry[key];
    final shown = point == null
        ? const PresentedValue(value: '--', unit: '', valid: false)
        : presentPoint(_rack.assetType, key, point);
    return MetricTile(label: label, value: shown.text, subtitle: shown.note, icon: icon, emphasis: emphasis);
  }

  List<double> _numericList(String key) {
    final value = _rack.telemetry[key]?.value;
    if (value is! List) return const [];
    return value.map((item) => item is num ? item.toDouble() : 0.0).toList();
  }
}

class CellChannelsView extends StatefulWidget {
  const CellChannelsView({
    super.key,
    required this.rackId,
    required this.voltages,
    required this.temperatures,
    required this.loading,
    required this.onReload,
    this.error,
  });

  final int rackId;
  final List<double> voltages;
  final List<double> temperatures;
  final bool loading;
  final String? error;
  final Future<void> Function() onReload;

  @override
  State<CellChannelsView> createState() => _CellChannelsViewState();
}

class _CellChannelsViewState extends State<CellChannelsView> {
  int _rowsPerPage = 25;
  int _page = 0;

  @override
  void didUpdateWidget(covariant CellChannelsView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.voltages.length != widget.voltages.length ||
        oldWidget.temperatures.length != widget.temperatures.length) {
      _page = 0;
    }
  }

  @override
  Widget build(BuildContext context) {
    final voltageCount = _populatedCount(widget.voltages);
    final temperatureCount = _populatedCount(widget.temperatures);
    final rowCount = math.max(voltageCount, temperatureCount);
    final activeVoltages = widget.voltages.take(voltageCount).where((value) => value > 0).toList();
    final activeTemps = widget.temperatures.take(temperatureCount).where((value) => value != 0).toList();
    final avgVoltage = activeVoltages.isEmpty
        ? 0.0
        : activeVoltages.reduce((a, b) => a + b) / activeVoltages.length;

    if (rowCount == 0) {
      return ListView(
        padding: const EdgeInsets.all(20),
        children: [
          SectionHeader(
            'Rack ${widget.rackId} cell channels',
            subtitle: 'Complete cell voltage and temperature arrays are loaded from the rack-detail API.',
          ),
          const SizedBox(height: 16),
          if (widget.loading) ...[
            const LinearProgressIndicator(),
            const SizedBox(height: 12),
            const Text('Loading complete rack data…'),
          ] else
            Card(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Cell arrays are not loaded yet.',
                      style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16),
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'Press the button below to fetch the complete voltage and temperature arrays for this rack.',
                    ),
                    if (widget.error != null) ...[
                      const SizedBox(height: 10),
                      Text(widget.error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                    ],
                    const SizedBox(height: 14),
                    FilledButton.icon(
                      onPressed: widget.onReload,
                      icon: const Icon(Icons.download),
                      label: const Text('Load complete rack data'),
                    ),
                  ],
                ),
              ),
            ),
        ],
      );
    }

    final pageCount = (rowCount + _rowsPerPage - 1) ~/ _rowsPerPage;
    final safePage = _page >= pageCount ? pageCount - 1 : _page;
    final start = safePage * _rowsPerPage;
    final end = math.min(start + _rowsPerPage, rowCount);

    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        SectionHeader(
          'Rack ${widget.rackId} cell channels',
          subtitle:
              '$voltageCount populated voltage channels • $temperatureCount populated temperature channels. '
              'Temperature channels are displayed by channel index because the payload does not provide a complete cell-to-temperature-sensor map.',
        ),
        if (widget.loading) ...[
          const SizedBox(height: 12),
          const LinearProgressIndicator(),
        ],
        if (widget.error != null) ...[
          const SizedBox(height: 12),
          Card(
            color: Theme.of(context).colorScheme.errorContainer,
            child: ListTile(
              leading: const Icon(Icons.error_outline),
              title: const Text('Could not refresh complete rack data'),
              subtitle: Text(widget.error!),
              trailing: IconButton(onPressed: widget.onReload, icon: const Icon(Icons.refresh)),
            ),
          ),
        ],
        const SizedBox(height: 16),
        MetricGrid(children: [
          MetricTile(label: 'Populated cells', value: '$voltageCount', icon: Icons.grid_4x4),
          MetricTile(label: 'Temperature channels', value: '$temperatureCount', icon: Icons.thermostat),
          MetricTile(
            label: 'Voltage range',
            value: activeVoltages.isEmpty
                ? '--'
                : '${activeVoltages.reduce((a, b) => a < b ? a : b).toStringAsFixed(0)}–${activeVoltages.reduce((a, b) => a > b ? a : b).toStringAsFixed(0)} mV',
            icon: Icons.battery_5_bar,
          ),
          MetricTile(
            label: 'Temperature range',
            value: activeTemps.isEmpty
                ? '--'
                : '${activeTemps.reduce((a, b) => a < b ? a : b).toStringAsFixed(1)}–${activeTemps.reduce((a, b) => a > b ? a : b).toStringAsFixed(1)} °C',
            icon: Icons.device_thermostat,
          ),
        ]),
        const SizedBox(height: 16),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Wrap(
              spacing: 12,
              runSpacing: 10,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Text('Showing ${start + 1}–$end of $rowCount channels'),
                DropdownButton<int>(
                  value: _rowsPerPage,
                  items: const [10, 25, 50, 100]
                      .map((value) => DropdownMenuItem(value: value, child: Text('$value rows')))
                      .toList(),
                  onChanged: (value) {
                    if (value != null) {
                      setState(() {
                        _rowsPerPage = value;
                        _page = 0;
                      });
                    }
                  },
                ),
                IconButton(
                  tooltip: 'Previous page',
                  onPressed: safePage > 0 ? () => setState(() => _page = safePage - 1) : null,
                  icon: const Icon(Icons.chevron_left),
                ),
                Text('Page ${safePage + 1} of $pageCount'),
                IconButton(
                  tooltip: 'Next page',
                  onPressed: safePage + 1 < pageCount ? () => setState(() => _page = safePage + 1) : null,
                  icon: const Icon(Icons.chevron_right),
                ),
                OutlinedButton.icon(
                  onPressed: widget.loading ? null : widget.onReload,
                  icon: const Icon(Icons.refresh),
                  label: const Text('Refresh arrays'),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),
        Card(
          clipBehavior: Clip.antiAlias,
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: ConstrainedBox(
              constraints: const BoxConstraints(minWidth: 920),
              child: Column(
                children: [
                  const _CellTableRow(
                    indexLabel: 'Cell / channel',
                    voltageLabel: 'Voltage',
                    temperatureLabel: 'Temperature',
                    deviationLabel: 'Voltage deviation',
                    conditionLabel: 'Condition',
                    header: true,
                  ),
                  for (var index = start; index < end; index++)
                    _buildCellRow(index, avgVoltage),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildCellRow(int index, double averageVoltage) {
    final voltage = index < widget.voltages.length && widget.voltages[index] != 0
        ? widget.voltages[index]
        : null;
    final temperature = index < widget.temperatures.length && widget.temperatures[index] != 0
        ? widget.temperatures[index]
        : null;
    final deviation = voltage == null ? null : voltage - averageVoltage;
    final condition = _condition(voltage, temperature, deviation);
    return _CellTableRow(
      indexLabel: '${index + 1}',
      voltageLabel: voltage == null ? '--' : '${voltage.toStringAsFixed(0)} mV',
      temperatureLabel: temperature == null ? '--' : '${temperature.toStringAsFixed(1)} °C',
      deviationLabel: deviation == null
          ? '--'
          : '${deviation >= 0 ? '+' : ''}${deviation.toStringAsFixed(1)} mV',
      conditionLabel: condition.$1,
      conditionIcon: condition.$2,
      conditionColor: condition.$3,
      alternate: index.isOdd,
    );
  }

  (String, IconData, Color) _condition(double? voltage, double? temperature, double? deviation) {
    if (voltage == null && temperature == null) {
      return ('No data', Icons.remove_circle_outline, Colors.grey);
    }
    if (temperature != null && temperature >= 45) {
      return ('High temperature', Icons.warning, Colors.red);
    }
    if (deviation != null && deviation.abs() >= 30) {
      return ('Voltage outlier', Icons.warning, Colors.orange);
    }
    return ('Normal', Icons.check_circle, Colors.green);
  }

  int _populatedCount(List<double> values) {
    for (var index = values.length - 1; index >= 0; index--) {
      if (values[index] != 0) return index + 1;
    }
    return 0;
  }
}

class _CellTableRow extends StatelessWidget {
  const _CellTableRow({
    required this.indexLabel,
    required this.voltageLabel,
    required this.temperatureLabel,
    required this.deviationLabel,
    required this.conditionLabel,
    this.conditionIcon,
    this.conditionColor,
    this.header = false,
    this.alternate = false,
  });

  final String indexLabel;
  final String voltageLabel;
  final String temperatureLabel;
  final String deviationLabel;
  final String conditionLabel;
  final IconData? conditionIcon;
  final Color? conditionColor;
  final bool header;
  final bool alternate;

  @override
  Widget build(BuildContext context) {
    final style = header
        ? Theme.of(context).textTheme.labelLarge?.copyWith(fontWeight: FontWeight.w800)
        : Theme.of(context).textTheme.bodyMedium;
    return Container(
      color: header
          ? Theme.of(context).colorScheme.surfaceContainerHighest
          : alternate
              ? Theme.of(context).colorScheme.surfaceContainerLow.withOpacity(0.55)
              : null,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        children: [
          _cell(indexLabel, 120, style, bold: !header),
          _cell(voltageLabel, 150, style),
          _cell(temperatureLabel, 160, style),
          _cell(deviationLabel, 190, style),
          SizedBox(
            width: 250,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (conditionIcon != null) ...[
                  Icon(conditionIcon, size: 18, color: conditionColor),
                  const SizedBox(width: 6),
                ],
                Flexible(child: Text(conditionLabel, style: style, overflow: TextOverflow.ellipsis)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _cell(String value, double width, TextStyle? style, {bool bold = false}) {
    return SizedBox(
      width: width,
      child: Text(
        value,
        style: bold ? style?.copyWith(fontWeight: FontWeight.w700) : style,
        overflow: TextOverflow.ellipsis,
      ),
    );
  }
}

class SensorArraySection extends StatelessWidget {
  const SensorArraySection({super.key, required this.title, required this.values, required this.unit});

  final String title;
  final List<double> values;
  final String unit;

  @override
  Widget build(BuildContext context) {
    final populated = <MapEntry<int, double>>[];
    for (var i = 0; i < values.length; i++) {
      if (values[i] != 0) populated.add(MapEntry(i + 1, values[i]));
    }
    return Card(
      child: ExpansionTile(
        initiallyExpanded: populated.isNotEmpty,
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
        subtitle: Text('${populated.length} populated channels'),
        children: [
          if (populated.isEmpty)
            const Padding(padding: EdgeInsets.all(16), child: Text('No populated values reported.'))
          else
            Padding(
              padding: const EdgeInsets.all(12),
              child: Wrap(
                spacing: 8,
                runSpacing: 8,
                children: populated
                    .map((entry) => Chip(label: Text('Ch ${entry.key}: ${entry.value.toStringAsFixed(1)} $unit')))
                    .toList(),
              ),
            ),
        ],
      ),
    );
  }
}
