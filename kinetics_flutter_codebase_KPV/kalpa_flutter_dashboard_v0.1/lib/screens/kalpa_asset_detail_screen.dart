import 'dart:convert';
import 'package:flutter/material.dart';
import '../core/presentation/kalpa_asset_presentation.dart';
import '../core/state/gateway_controller.dart';
import '../models/gateway_models.dart';
import '../widgets/common_widgets.dart';

class KalpaAssetScreen extends StatefulWidget {
  const KalpaAssetScreen({
    super.key,
    required this.controller,
    required this.assetId,
  });
  final GatewayController controller;
  final String assetId;
  @override
  State<KalpaAssetScreen> createState() => _KalpaAssetScreenState();
}

class _KalpaAssetScreenState extends State<KalpaAssetScreen> {
  bool _loading = false;
  String? _error;

  Future<void> _loadCompleteRack(AssetSnapshot asset) async {
    if (_loading || asset.rackId == null) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await widget.controller.loadRackDetails(asset.rackId!);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
    animation: widget.controller,
    builder: (context, _) {
      final asset = widget.controller.plant.assets[widget.assetId];
      if (asset == null) {
        return Scaffold(
          appBar: AppBar(title: Text(widget.assetId)),
          body: const Center(
            child: Text('No cached telemetry for this asset yet.'),
          ),
        );
      }
      final tabs = kalpaTabs(asset.assetType);
      final groups = kalpaGrouped(asset);
      final label =
          asset.label ??
          (asset.assetType == 'bms_rack'
              ? 'Rack ${asset.rackId ?? asset.assetId.replaceFirst('bms_rack_', '')}'
              : asset.assetType == 'bms_bank'
              ? 'System BMS'
              : prettifyKey(asset.assetId));
      return DefaultTabController(
        key: ValueKey('${asset.assetId}:${asset.assetType}'),
        length: tabs.length,
        child: Scaffold(
          appBar: AppBar(
            title: Text(label),
            actions: [
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 12),
                child: StatusPill(
                  label: asset.online ? 'Online' : 'Offline',
                  good: asset.online,
                ),
              ),
              if (asset.assetType == 'bms_rack')
                IconButton(
                  tooltip: 'Load complete rack data',
                  onPressed: _loading || !widget.controller.authenticated
                      ? null
                      : () => _loadCompleteRack(asset),
                  icon: _loading
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.download),
                ),
              IconButton(
                tooltip: 'Refresh cached signals',
                onPressed: widget.controller.busy
                    ? null
                    : widget.controller.refreshKalpa,
                icon: const Icon(Icons.refresh),
              ),
              const SizedBox(width: 8),
            ],
            bottom: TabBar(
              isScrollable: true,
              tabs: tabs.map((tab) => Tab(text: tab.title)).toList(),
            ),
          ),
          body: TabBarView(
            children: tabs.map((tab) => _page(asset, tab, groups)).toList(),
          ),
        ),
      );
    },
  );

  Widget _page(
    AssetSnapshot asset,
    KalpaDetailTab tab,
    Map<String, List<MapEntry<String, TelemetryPoint>>> groups,
  ) {
    if (tab.id == 'all') {
      return ListView(
        padding: const EdgeInsets.all(20),
        children: [
          const SectionHeader(
            'All signals',
            subtitle: 'Advanced register view · search every published point',
          ),
          const SizedBox(height: 16),
          KalpaCategoryTable(
            key: ValueKey('${asset.assetId}:all'),
            asset: asset,
            title: 'All published signals',
            entries: asset.telemetry.entries.toList(),
          ),
        ],
      );
    }
    final overview = tab.id == 'overview';
    final sections = kalpaGroups.where((group) {
      if ((groups[group.id] ?? []).isEmpty) return false;
      final target = kalpaTabFor(asset.assetType, group);
      if (target == tab.id) return true;
      // As in the original Kinetics dashboard, the overview combines operating
      // state with a short electrical/measurement summary; bulk channels stay
      // on their dedicated tabs.
      if (!overview) return false;
      return ['operating', 'communication', 'other'].contains(group.id) ||
          (asset.assetType == 'pcs' && ['dc', 'ac'].contains(group.id)) ||
          (['bms_rack', 'bms_bank'].contains(asset.assetType) &&
              ['electrical', 'capability'].contains(group.id)) ||
          (kalpaRole(asset.assetType) == 'environment' &&
              ['cooling', 'humidity', 'inputs'].contains(group.id));
    }).toList();
    final children = <Widget>[
      SectionHeader(
        overview ? '${_title(asset)} overview' : tab.title,
        subtitle:
            '${asset.telemetry.length} published signals · ${asset.assetId} · ${_time(asset.timestamp)}',
      ),
      if (!asset.online)
        const Padding(
          padding: EdgeInsets.symmetric(vertical: 12),
          child: Text(
            'Asset offline. Retained readings are hidden until communication recovers.',
          ),
        ),
      if (_error != null)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 12),
          child: Text('Complete rack data unavailable: $_error'),
        ),
      const SizedBox(height: 16),
    ];
    if (overview) {
      children.add(MetricGrid(children: _metrics(asset)));
      children.add(const SizedBox(height: 18));
      if (['bms_rack', 'bms_bank'].contains(asset.assetType)) {
        children.add(
          const Padding(
            padding: EdgeInsets.only(bottom: 16),
            child: Text(
              'Lineage battery current: positive = charging, negative = discharging.',
            ),
          ),
        );
      }
    }
    if (tab.id == 'cells') {
      final voltages = (groups['cell_voltage'] ?? [])
          .where(
            (entry) =>
                kalpaPointAvailable(asset, entry.value) &&
                entry.value.value is num,
          )
          .map((entry) => (entry.value.value as num).toDouble())
          .toList();
      final temperatures = (groups['cell_temperature'] ?? [])
          .where(
            (entry) =>
                kalpaPointAvailable(asset, entry.value) &&
                entry.value.value is num,
          )
          .map((entry) => (entry.value.value as num).toDouble())
          .toList();
      String range(List<double> values, String unit) {
        if (values.isEmpty) return '—';
        values.sort();
        return '${values.first.toStringAsFixed(3)}–${values.last.toStringAsFixed(3)} $unit';
      }

      children.add(
        MetricGrid(
          children: [
            MetricTile(
              label: 'Published cell voltages',
              value: '${groups['cell_voltage']?.length ?? 0}',
              icon: Icons.grid_4x4,
            ),
            MetricTile(
              label: 'Temperature channels',
              value: '${groups['cell_temperature']?.length ?? 0}',
              icon: Icons.thermostat,
            ),
            MetricTile(
              label: 'Cell voltage range',
              value: range(voltages, 'V'),
              icon: Icons.bolt,
            ),
            MetricTile(
              label: 'Cell temperature range',
              value: range(temperatures, '°C'),
              icon: Icons.device_thermostat,
            ),
          ],
        ),
      );
      children.add(const SizedBox(height: 18));
      children.add(
        const Padding(
          padding: EdgeInsets.only(bottom: 16),
          child: Text(
            'Cell channels are grouped by voltage, temperature, SOC and balancing. '
            'Only received channels are shown; unavailable values are never converted to zero. '
            'Use Load complete rack data in the toolbar if bulk channels have not been cached.',
          ),
        ),
      );
    }
    if (tab.id == 'settings') {
      children.add(
        const Padding(
          padding: EdgeInsets.only(bottom: 16),
          child: Text('Read-only configuration and commissioning values.'),
        ),
      );
    }
    if (['status', 'alarms'].contains(tab.id) || overview) {
      final bits = _decodedBits(asset, alarmOnly: tab.id == 'alarms');
      if (bits.isNotEmpty)
        children.add(
          _BitTable(
            title: tab.id == 'alarms'
                ? 'Decoded alarm / fault bits'
                : 'Decoded operating and safety flags',
            rows: bits,
          ),
        );
      if (tab.id == 'alarms') {
        final alarms = widget.controller.activeAlarms
            .where(
              (alarm) =>
                  alarm['asset_id'] == asset.assetId ||
                  alarm['source'] == asset.assetId,
            )
            .toList();
        if (alarms.isNotEmpty)
          children.add(
            Card(
              child: Column(
                children: alarms
                    .map(
                      (alarm) => ListTile(
                        leading: const Icon(Icons.warning_amber),
                        title: Text(
                          '${alarm['message'] ?? alarm['alarm_key'] ?? 'Gateway alarm'}',
                        ),
                        subtitle: Text(
                          '${alarm['severity'] ?? ''} · ${alarm['timestamp'] ?? ''}',
                        ),
                      ),
                    )
                    .toList(),
              ),
            ),
          );
      }
    }
    for (final group in sections) {
      children.add(
        Padding(
          padding: const EdgeInsets.only(bottom: 18),
          child: KalpaCategoryTable(
            key: ValueKey('${asset.assetId}:${group.id}'),
            asset: asset,
            title: group.title,
            entries: groups[group.id]!,
          ),
        ),
      );
    }
    if (sections.isEmpty)
      children.add(
        Card(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Text(
              'No ${tab.title.toLowerCase()} signals published for this asset.',
            ),
          ),
        ),
      );
    children.add(const SizedBox(height: 24));
    return ListView(
      key: PageStorageKey('${asset.assetId}:${tab.id}'),
      padding: const EdgeInsets.all(20),
      children: children,
    );
  }

  String _title(AssetSnapshot asset) => asset.assetType == 'bms_rack'
      ? 'Rack ${asset.rackId ?? asset.assetId.replaceFirst('bms_rack_', '')}'
      : asset.assetType == 'bms_bank'
      ? 'System BMS'
      : asset.label ?? prettifyKey(asset.assetId);
  String _time(String? value) =>
      DateTime.tryParse(value ?? '')?.toLocal().toString().split('.').first ??
      'No timestamp';

  List<Widget> _metrics(AssetSnapshot asset) {
    final keys = asset.assetType == 'bms_rack'
        ? [
            'rack_voltage',
            'rack_current',
            'rack_soc',
            'rack_soh',
            'rack_max_cell_voltage',
            'rack_min_cell_voltage',
            'rack_max_cell_temperature',
            'rack_min_cell_temperature',
          ]
        : asset.assetType == 'bms_bank'
        ? [
            'system_voltage',
            'system_current',
            'system_soc',
            'system_soh',
            'system_max_charge_power',
            'system_max_discharge_power',
            'system_max_cell_voltage',
            'system_min_cell_voltage',
          ]
        : asset.assetType == 'pcs'
        ? [
            'total_active_power',
            'total_reactive_power',
            'dc_voltage',
            'dc_current',
            'dc_bus_voltage',
            'total_power_factor',
            'grid_frequency_a',
            'converter_efficiency',
          ]
        : asset.telemetry.entries
              .where(
                (entry) =>
                    ['cooling', 'humidity', 'operating', 'inputs'].contains(
                      kalpaGroupFor(asset.assetType, entry.key, entry.value),
                    ),
              )
              .take(6)
              .map((e) => e.key)
              .toList();
    if (keys.isEmpty)
      return [
        const MetricTile(label: 'Cached signals', value: 'No measurements'),
      ];
    return keys.map((key) {
      final point = asset.point(key);
      final value = point == null ? '—' : kalpaPointValue(asset, key, point);
      final unit = point == null
          ? ''
          : kalpaPointUnit(asset.assetType, key, point);
      return MetricTile(
        label: kalpaPointName(
          asset.assetType,
          key,
          point ?? const TelemetryPoint(value: null, quality: 'missing'),
        ),
        value: value == '—' || unit.isEmpty ? value : '$value $unit',
        icon: key.contains('temp')
            ? Icons.thermostat
            : key.contains('soc')
            ? Icons.battery_5_bar
            : Icons.electric_bolt,
        emphasis: true,
      );
    }).toList();
  }

  List<List<String>> _decodedBits(
    AssetSnapshot asset, {
    required bool alarmOnly,
  }) {
    final result = <List<String>>[];
    for (final entry in asset.telemetry.entries) {
      final group = kalpaGroupFor(asset.assetType, entry.key, entry.value);
      if (alarmOnly ? group != 'alarms' : group != 'operating') continue;
      final point = entry.value;
      final meta = kalpaMetadata(asset.assetType, entry.key);
      final bits = meta['bitfields'];
      if (bits is! List || point.value is! num) continue;
      for (final bit in bits.whereType<Map>()) {
        final index = bit['bit'];
        if (index is! int) continue;
        result.add([
          '${bit['name_en'] ?? bit['key'] ?? 'Bit $index'}',
          kalpaPointAvailable(asset, point)
              ? '${(point.value.toInt() >> index) & 1}'
              : '—',
          '${bit['value_text'] ?? ''}',
          '${entry.key} · bit $index',
        ]);
      }
    }
    return result;
  }
}

class _BitTable extends StatelessWidget {
  const _BitTable({required this.title, required this.rows});
  final String title;
  final List<List<String>> rows;
  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 10),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: DataTable(
              columns: const [
                DataColumn(label: Text('Flag')),
                DataColumn(label: Text('Value')),
                DataColumn(label: Text('Protocol meaning')),
                DataColumn(label: Text('Source')),
              ],
              rows: rows
                  .map(
                    (row) => DataRow(
                      cells: row.map((text) => DataCell(Text(text))).toList(),
                    ),
                  )
                  .toList(),
            ),
          ),
        ],
      ),
    ),
  );
}

class KalpaCategoryTable extends StatefulWidget {
  const KalpaCategoryTable({
    super.key,
    required this.asset,
    required this.title,
    required this.entries,
  });
  final AssetSnapshot asset;
  final String title;
  final List<MapEntry<String, TelemetryPoint>> entries;
  @override
  State<KalpaCategoryTable> createState() => _KalpaCategoryTableState();
}

class _KalpaCategoryTableState extends State<KalpaCategoryTable> {
  String query = '';
  int page = 0;
  static const pageSize = 20;
  @override
  void didUpdateWidget(covariant KalpaCategoryTable oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.asset.assetId != widget.asset.assetId) {
      page = 0;
      query = '';
    }
  }

  @override
  Widget build(BuildContext context) {
    final entries = widget.entries.where((entry) {
      final point = entry.value;
      return '${entry.key} ${kalpaPointName(widget.asset.assetType, entry.key, point)} '
              '${kalpaPointAddress(widget.asset.assetType, entry.key, point)} '
              '${kalpaPointValue(widget.asset, entry.key, point)}'
          .toLowerCase()
          .contains(query.toLowerCase());
    }).toList()..sort((a, b) => kalpaNaturalCompare(a.key, b.key));
    final pages = (entries.length / pageSize).ceil();
    final current = page.clamp(0, pages == 0 ? 0 : pages - 1).toInt();
    final visible = entries.skip(current * pageSize).take(pageSize);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              widget.title,
              style: Theme.of(
                context,
              ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 4),
            Text(
              '${widget.entries.length} published signals · ${entries.length} matching',
            ),
            const SizedBox(height: 12),
            TextField(
              key: ValueKey('search:${widget.title}'),
              decoration: const InputDecoration(
                labelText: 'Search this category',
                prefixIcon: Icon(Icons.search),
                border: OutlineInputBorder(),
              ),
              onChanged: (value) => setState(() {
                query = value;
                page = 0;
              }),
            ),
            const SizedBox(height: 12),
            // DataTable has no flex header. Its bounded viewport scrolls horizontally
            // while rows are paged locally to avoid building thousands of cell rows.
            LayoutBuilder(
              builder: (context, constraints) => SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: ConstrainedBox(
                  constraints: BoxConstraints(minWidth: constraints.maxWidth),
                  child: DataTable(
                    showCheckboxColumn: false,
                    columnSpacing: 24,
                    columns: const [
                      DataColumn(label: Text('Parameter')),
                      DataColumn(label: Text('Value')),
                      DataColumn(label: Text('Unit')),
                      DataColumn(label: Text('Quality')),
                      DataColumn(label: Text('Register')),
                    ],
                    rows: visible.map((entry) {
                      final point = entry.value;
                      return DataRow(
                        cells: [
                          DataCell(
                            SizedBox(
                              width: 280,
                              child: Column(
                                mainAxisAlignment: MainAxisAlignment.center,
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    kalpaPointName(
                                      widget.asset.assetType,
                                      entry.key,
                                      point,
                                    ),
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                  Text(
                                    entry.key,
                                    style: Theme.of(
                                      context,
                                    ).textTheme.bodySmall,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ],
                              ),
                            ),
                            onTap: () => _showPoint(entry),
                          ),
                          DataCell(
                            Text(
                              kalpaPointValue(widget.asset, entry.key, point),
                            ),
                            onTap: () => _showPoint(entry),
                          ),
                          DataCell(
                            Text(
                              kalpaPointUnit(
                                widget.asset.assetType,
                                entry.key,
                                point,
                              ),
                            ),
                          ),
                          DataCell(
                            Text(
                              widget.asset.online ? point.quality : 'offline',
                            ),
                          ),
                          DataCell(
                            Text(
                              kalpaPointAddress(
                                widget.asset.assetType,
                                entry.key,
                                point,
                              ),
                            ),
                          ),
                        ],
                      );
                    }).toList(),
                  ),
                ),
              ),
            ),
            if (entries.isEmpty)
              const Padding(
                padding: EdgeInsets.all(16),
                child: Text('No signals match this search.'),
              ),
            Wrap(
              alignment: WrapAlignment.end,
              crossAxisAlignment: WrapCrossAlignment.center,
              spacing: 8,
              children: [
                Text(
                  entries.isEmpty
                      ? '0 signals'
                      : '${current * pageSize + 1}–${(current * pageSize + pageSize).clamp(0, entries.length)} of ${entries.length}',
                ),
                IconButton(
                  tooltip: 'Previous page',
                  onPressed: current == 0
                      ? null
                      : () => setState(() => page = current - 1),
                  icon: const Icon(Icons.chevron_left),
                ),
                IconButton(
                  tooltip: 'Next page',
                  onPressed: current + 1 >= pages
                      ? null
                      : () => setState(() => page = current + 1),
                  icon: const Icon(Icons.chevron_right),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  void _showPoint(MapEntry<String, TelemetryPoint> entry) => showDialog<void>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(
        kalpaPointName(widget.asset.assetType, entry.key, entry.value),
      ),
      content: SizedBox(
        width: 700,
        height: 400,
        child: SingleChildScrollView(
          child: SelectableText(
            const JsonEncoder.withIndent('  ').convert({
              'key': entry.key,
              'telemetry': entry.value.toJson(),
              'protocol_metadata': kalpaMetadata(
                widget.asset.assetType,
                entry.key,
              ),
            }),
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Close'),
        ),
      ],
    ),
  );
}
