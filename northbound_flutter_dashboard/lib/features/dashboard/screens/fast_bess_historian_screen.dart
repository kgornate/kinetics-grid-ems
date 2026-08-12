import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/api/northbound_api_client.dart';
import '../../../core/download/file_download.dart';
import '../../../core/export/fast_bess_history_exporter.dart';
import '../../auth/models/auth_session.dart';
import '../../auth/screens/environment_select_screen.dart';
import '../../auth/services/session_store.dart';
import '../widgets/dashboard_nav_actions.dart';

class FastBessHistorianScreen extends StatefulWidget {
  final AuthSession session;
  final ValueChanged<DashboardPage>? onNavigate;
  final Future<void> Function()? onLogout;

  const FastBessHistorianScreen({
    super.key,
    required this.session,
    this.onNavigate,
    this.onLogout,
  });

  @override
  State<FastBessHistorianScreen> createState() => _FastBessHistorianScreenState();
}

class _SignalOption {
  const _SignalOption({required this.assetType, required this.name});

  final String assetType;
  final String name;

  String get key => '$assetType:$name';
  String get label => '${assetType.toUpperCase()} $name';
}

class _FastBessHistorianScreenState extends State<FastBessHistorianScreen> {
  static const _defaultLimit = 600;
  static const _maxTableRows = 1000;

  bool _bootLoading = true;
  bool _refreshing = false;
  bool _historyLoading = false;
  bool _exporting = false;
  String? _error;
  String? _exportMessage;

  Map<String, dynamic>? _status;
  Map<String, dynamic>? _profile;
  List<Map<String, dynamic>> _latestItems = const [];
  List<Map<String, dynamic>> _historyItems = const [];

  String _selectedSource = 'all';
  String _assetFilter = 'both';
  String _timeRange = '15m';
  int _limit = _defaultLimit;
  String _order = 'desc';
  final Set<String> _selectedSignalKeys = <String>{};

  Timer? _statusTimer;

  static const List<String> _fallbackPcsSignals = [
    'phase_a_voltage',
    'phase_b_voltage',
    'phase_c_voltage',
    'phase_a_current',
    'phase_b_current',
    'phase_c_current',
    'dc_voltage',
    'dc_current',
    'grid_frequency',
    'charge_discharge_power',
    'total_active_power',
    'soc',
    'fault_status',
    'total_fault_status',
    'total_alarm_status',
    'on_grid_status',
    'off_grid_status',
    'running_status_2',
    'pcs_online_status',
    'bms_online_status',
    'sw_fault_ac_over_voltage',
    'sw_fault_ac_under_voltage',
    'sw_fault_ac_over_frequency',
    'sw_fault_ac_under_frequency',
    'sw_fault_ac_over_current',
    'hw_fault_ac_over_current',
    'sw_fault_dc_charge_over_current',
    'sw_fault_dc_discharge_over_current',
  ];

  static const List<String> _fallbackBmsSignals = [
    'cluster_total_voltage_collected',
    'cluster_total_current',
    'can_hall_sampling_current',
    'display_soc',
    'soh',
    'cell_max_voltage',
    'cell_min_voltage',
    'max_min_cell_voltage_diff',
    'battery_max_temperature',
    'battery_min_temperature',
    'average_temperature',
    'insulation_resistance',
    'pre_charge_total_voltage',
    'system_status',
    'charge_discharge_status',
    'pre_charge_contactor_status',
    'negative_contactor_status',
    'contactor_fault',
    'fuse_fault',
    'insulation_fault',
    'insulation_monitoring_fault',
    'battery_temperature_sensor_fault',
    'voltage_sampling_fault',
    'current_sampling_fault_functional_safety_fault',
    'charge_over_current',
    'discharge_over_current_level_1',
    'bmu_communication_fault',
    'bau_communication_fault',
    'pcs_communication_fault',
    'cell_over_voltage_level_1',
    'cell_under_voltage_level_1',
    'battery_pack_over_voltage_alarm_voltage_value',
    'battery_pack_under_voltage_alarm_voltage_value',
    'battery_charge_over_current_alarm_current_value',
    'battery_discharge_over_current_alarm_current_value',
  ];

  static const List<String> _defaultSelectedKeys = [
    'pcs:dc_voltage',
    'pcs:dc_current',
    'pcs:grid_frequency',
    'pcs:charge_discharge_power',
    'pcs:total_active_power',
    'pcs:fault_status',
    'pcs:total_alarm_status',
    'bms:cluster_total_voltage_collected',
    'bms:cluster_total_current',
    'bms:display_soc',
    'bms:soh',
    'bms:battery_max_temperature',
    'bms:insulation_resistance',
    'bms:contactor_fault',
    'bms:insulation_fault',
    'bms:pcs_communication_fault',
  ];

  @override
  void initState() {
    super.initState();
    _selectedSignalKeys.addAll(_defaultSelectedKeys);
    _loadInitial();
    _statusTimer = Timer.periodic(const Duration(seconds: 10), (_) => _refreshStatus(silent: true));
  }

  @override
  void dispose() {
    _statusTimer?.cancel();
    super.dispose();
  }

  NorthboundApiClient _api() => NorthboundApiClient(
        baseUrl: widget.session.connection.baseUrl,
        token: widget.session.accessToken,
      );

  Future<void> _loadInitial() async {
    setState(() {
      _bootLoading = true;
      _error = null;
    });
    try {
      final api = _api();
      final status = await api.getFastBessStatus();
      final profile = await api.getFastBessProfile();
      final latest = await api.getFastBessLatest(format: 'compact');
      if (!mounted) return;
      setState(() {
        _status = status;
        _profile = profile;
        _latestItems = _items(latest);
        _bootLoading = false;
      });
    } catch (e) {
      await _handleError(e, boot: true);
    }
  }

  Future<void> _refreshStatus({bool silent = false}) async {
    if (!silent) {
      setState(() {
        _refreshing = true;
        _error = null;
      });
    }
    try {
      final api = _api();
      final status = await api.getFastBessStatus();
      final latest = await api.getFastBessLatest(format: 'compact');
      if (!mounted) return;
      setState(() {
        _status = status;
        _latestItems = _items(latest);
        _refreshing = false;
      });
    } catch (e) {
      await _handleError(e);
    }
  }

  Future<void> _loadHistory() async {
    setState(() {
      _historyLoading = true;
      _error = null;
    });
    try {
      final window = _selectedWindow();
      final api = _api();
      final history = await api.getFastBessHistory(
        sourceId: _selectedSource == 'all' ? null : _selectedSource,
        fromEpochMs: window.$1,
        toEpochMs: window.$2,
        limit: _limit,
        order: _order,
        format: 'compact',
      );
      if (!mounted) return;
      setState(() {
        _historyItems = _items(history);
        _historyLoading = false;
      });
    } catch (e) {
      await _handleError(e);
    }
  }


  Future<void> _exportCsv() async {
    await _exportLoadedHistory(format: 'csv');
  }

  Future<void> _exportXlsx() async {
    await _exportLoadedHistory(format: 'xlsx');
  }

  Future<void> _exportLoadedHistory({required String format}) async {
    if (_historyItems.isEmpty) {
      _showSnack('Load history first, then export the loaded table.');
      return;
    }

    final signals = _selectedSignals;
    if (signals.isEmpty) {
      _showSnack('Select at least one parameter before export.');
      return;
    }

    setState(() {
      _exporting = true;
      _error = null;
      _exportMessage = null;
    });

    try {
      final headers = _exportHeaders(signals);
      final rows = _exportRows(_historyItems, signals);
      final stamp = _fileStamp(DateTime.now());
      final sourceLabel = _selectedSource == 'all' ? 'all_bess' : _selectedSource;
      final baseName = 'fast_bess_history_${sourceLabel}_${_timeRange}_$stamp';

      final result = format == 'xlsx'
          ? await saveBytes(
              bytes: FastBessHistoryExporter.buildXlsxBytes(
                sheetName: 'Fast BESS History',
                headers: headers,
                rows: rows,
              ),
              fileName: '$baseName.xlsx',
              mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
          : await saveBytes(
              bytes: FastBessHistoryExporter.buildCsvBytes(
                headers: headers,
                rows: rows,
              ),
              fileName: '$baseName.csv',
              mimeType: 'text/csv;charset=utf-8',
            );

      if (!mounted) return;
      setState(() {
        _exporting = false;
        _exportMessage = result.userMessage;
      });
      _showSnack(result.userMessage);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _exporting = false;
        _error = 'Export failed: $e';
      });
    }
  }

  List<String> _exportHeaders(List<_SignalOption> signals) {
    return <String>[
      'Timestamp UTC',
      'Timestamp Local',
      'Source ID',
      'BESS ID',
      'Quality',
      'Max Data Age ms',
      'Selected Signal Count',
      'Good Signal Count',
      'Bad Signal Count',
      ...signals.map((signal) => signal.label),
    ];
  }

  List<List<Object?>> _exportRows(List<Map<String, dynamic>> items, List<_SignalOption> signals) {
    return items.map((item) {
      final pcs = _mapValue(item['pcs_values']);
      final bms = _mapValue(item['bms_values']);
      return <Object?>[
        _text(item['timestamp_utc']),
        _localTimestamp(item['timestamp_utc']),
        _text(item['source_id']),
        _text(item['bess_id']),
        _text(item['quality']),
        item['max_data_age_ms'],
        item['selected_signal_count'],
        item['good_signal_count'],
        item['bad_signal_count'],
        ...signals.map((signal) {
          final source = signal.assetType == 'pcs' ? pcs : bms;
          return _rawCellValue(source[signal.name]);
        }),
      ];
    }).toList(growable: false);
  }

  Future<void> _handleError(Object e, {bool boot = false}) async {
    final message = e.toString();
    if (message.contains('401') || message.contains('Unauthorized')) {
      await _logout();
      return;
    }
    if (!mounted) return;
    setState(() {
      _error = message;
      _bootLoading = false;
      _refreshing = false;
      _historyLoading = false;
      _exporting = false;
    });
  }

  Future<void> _logout() async {
    if (widget.onLogout != null) {
      await widget.onLogout!();
      return;
    }
    await SessionStore().clear();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const EnvironmentSelectScreen()),
      (route) => false,
    );
  }

  void _go(DashboardPage page) {
    if (page == DashboardPage.historian) return;
    widget.onNavigate?.call(page);
  }

  List<Map<String, dynamic>> _items(Map<String, dynamic> response) {
    return (response['items'] as List? ?? [])
        .whereType<Map<String, dynamic>>()
        .toList();
  }

  List<String> get _pcsSignals {
    final value = _profile?['pcs_signals'];
    if (value is List) return value.map((e) => e.toString()).toList();
    return _fallbackPcsSignals;
  }

  List<String> get _bmsSignals {
    final value = _profile?['bms_signals'];
    if (value is List) return value.map((e) => e.toString()).toList();
    return _fallbackBmsSignals;
  }

  List<_SignalOption> get _availableSignals {
    final options = <_SignalOption>[];
    if (_assetFilter == 'both' || _assetFilter == 'pcs') {
      options.addAll(_pcsSignals.map((name) => _SignalOption(assetType: 'pcs', name: name)));
    }
    if (_assetFilter == 'both' || _assetFilter == 'bms') {
      options.addAll(_bmsSignals.map((name) => _SignalOption(assetType: 'bms', name: name)));
    }
    return options;
  }

  List<_SignalOption> get _selectedSignals {
    final available = _availableSignals;
    final selected = available.where((e) => _selectedSignalKeys.contains(e.key)).toList();
    if (selected.isNotEmpty) return selected;
    return available.take(12).toList();
  }

  (int, int) _selectedWindow() {
    final now = DateTime.now().toUtc();
    Duration duration;
    switch (_timeRange) {
      case '5m':
        duration = const Duration(minutes: 5);
        break;
      case '1h':
        duration = const Duration(hours: 1);
        break;
      case '6h':
        duration = const Duration(hours: 6);
        break;
      case '24h':
        duration = const Duration(hours: 24);
        break;
      case '15m':
      default:
        duration = const Duration(minutes: 15);
        break;
    }
    final from = now.subtract(duration);
    return (from.millisecondsSinceEpoch, now.millisecondsSinceEpoch);
  }

  int _estimatedRows() {
    final seconds = switch (_timeRange) {
      '5m' => 5 * 60,
      '1h' => 60 * 60,
      '6h' => 6 * 60 * 60,
      '24h' => 24 * 60 * 60,
      _ => 15 * 60,
    };
    final sourceCount = _selectedSource == 'all' ? 2 : 1;
    return seconds * sourceCount;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('NorthBound EMS Dashboard'),
        actions: [
          DashboardNavActions(
            currentPage: DashboardPage.historian,
            connectionLabel: '${widget.session.connection.label} • ${widget.session.displayName}',
            onHome: () => _go(DashboardPage.home),
            onTopology: () => _go(DashboardPage.topology),
            onPcs: () => _go(DashboardPage.pcs),
            onBms: () => _go(DashboardPage.bms),
            onHistorian: () {},
            onChiller: () => _go(DashboardPage.chiller),
            onDehumidifier: () => _go(DashboardPage.dehumidifier),
            onFire: () => _go(DashboardPage.fire),
            onUtilityMeter: () => _go(DashboardPage.utilityMeter),
            onEmsSystem: () => _go(DashboardPage.emsSystem),
            onStrategy: () => _go(DashboardPage.strategy),
            onLogout: _logout,
            refreshing: _refreshing || _historyLoading,
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          await _refreshStatus();
          if (_historyItems.isNotEmpty) await _loadHistory();
        },
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            if (_bootLoading)
              const Padding(
                padding: EdgeInsets.all(40),
                child: Center(child: CircularProgressIndicator()),
              )
            else ...[
              if (_error != null) _errorCard(context),
              Text(
                'BESS Historian',
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 6),
              Text(
                '1-second compact PCS/BMS logger view. This page loads only selected time windows so the dashboard does not try to render 90 days of raw data at once.',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: const Color(0xFF5B6775)),
              ),
              const SizedBox(height: 16),
              _statusCards(context),
              const SizedBox(height: 16),
              _latestCard(context),
              const SizedBox(height: 16),
              _filterCard(context),
              const SizedBox(height: 16),
              _historyTableCard(context),
            ],
          ],
        ),
      ),
    );
  }

  Widget _errorCard(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Text(_error!, style: const TextStyle(color: Color(0xFFC53939))),
        ),
      ),
    );
  }

  Widget _statusCards(BuildContext context) {
    final status = _status ?? const <String, dynamic>{};
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: [
        _metricCard('Logger', _boolLabel(status['running']), 'Thread: ${_boolLabel(status['thread_alive'])}'),
        _metricCard('Mode', _text(status['execution_mode']), 'Write: ${_text(status['write_mode'])}'),
        _metricCard('Interval', '${_text(status['interval_sec'])} sec', 'Retention: ${_text(status['retention_days'])} days'),
        _metricCard('Profile', _text(status['profile_name']), 'Signals/BESS: ${_text(status['total_signal_count_per_bess'])}'),
        _metricCard('Samples', _text(status['sample_count']), 'Writes: ${_text(status['write_count'])}'),
        _metricCard('Last sample', _shortTime(status['last_sample_utc']), 'Skipped: ${_text(status['skipped_count'])}'),
      ],
    );
  }

  Widget _metricCard(String title, String value, String subtitle) {
    return SizedBox(
      width: 230,
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: const TextStyle(color: Color(0xFF6C7B8A), fontWeight: FontWeight.w600)),
              const SizedBox(height: 6),
              Text(value, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
              const SizedBox(height: 4),
              Text(subtitle, style: const TextStyle(color: Color(0xFF6C7B8A))),
            ],
          ),
        ),
      ),
    );
  }

  Widget _latestCard(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text('Latest Compact Samples', style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700)),
                ),
                FilledButton.tonalIcon(
                  onPressed: _refreshing ? null : () => _refreshStatus(),
                  icon: const Icon(Icons.refresh_rounded),
                  label: const Text('Refresh latest'),
                ),
              ],
            ),
            const SizedBox(height: 12),
            if (_latestItems.isEmpty)
              const Text('No latest samples returned yet.')
            else
              Wrap(
                spacing: 12,
                runSpacing: 12,
                children: _latestItems.map((item) => _latestSampleTile(item)).toList(),
              ),
          ],
        ),
      ),
    );
  }

  Widget _latestSampleTile(Map<String, dynamic> item) {
    final pcs = _mapValue(item['pcs_values']);
    final bms = _mapValue(item['bms_values']);
    return SizedBox(
      width: 390,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: const Color(0xFFF8FAFD),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: const Color(0xFFE6EBF2)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${_text(item['bess_id'])} • ${_text(item['source_id'])}', style: const TextStyle(fontWeight: FontWeight.w800)),
            const SizedBox(height: 6),
            Text('Time: ${_shortTime(item['timestamp_utc'])} • Quality: ${_text(item['quality'])}'),
            const SizedBox(height: 8),
            Text('PCS DC: ${_valueText(pcs['dc_voltage'])} V, ${_valueText(pcs['dc_current'])} A, Freq ${_valueText(pcs['grid_frequency'])} Hz'),
            Text('BMS: ${_valueText(bms['cluster_total_voltage_collected'])} V, ${_valueText(bms['cluster_total_current'])} A, SOC ${_valueText(bms['display_soc'])}%'),
          ],
        ),
      ),
    );
  }

  Widget _filterCard(BuildContext context) {
    final estimated = _estimatedRows();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('History Filters', style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700)),
            const SizedBox(height: 12),
            Wrap(
              spacing: 12,
              runSpacing: 12,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                _dropdown(
                  label: 'BESS',
                  value: _selectedSource,
                  items: const {
                    'all': 'All BESS',
                    'external_ems_1': 'BESS 1',
                    'external_ems_2': 'BESS 2',
                  },
                  onChanged: (value) => setState(() => _selectedSource = value),
                ),
                _dropdown(
                  label: 'Asset',
                  value: _assetFilter,
                  items: const {'both': 'PCS + BMS', 'pcs': 'PCS only', 'bms': 'BMS only'},
                  onChanged: (value) => setState(() => _assetFilter = value),
                ),
                _dropdown(
                  label: 'Time range',
                  value: _timeRange,
                  items: const {'5m': 'Last 5 min', '15m': 'Last 15 min', '1h': 'Last 1 hour', '6h': 'Last 6 hours', '24h': 'Last 24 hours'},
                  onChanged: (value) => setState(() => _timeRange = value),
                ),
                _dropdown(
                  label: 'Limit',
                  value: '$_limit',
                  items: const {'200': '200 rows', '600': '600 rows', '1000': '1000 rows', '2000': '2000 rows', '5000': '5000 rows'},
                  onChanged: (value) => setState(() => _limit = int.tryParse(value) ?? _defaultLimit),
                ),
                _dropdown(
                  label: 'Order',
                  value: _order,
                  items: const {'desc': 'Latest first', 'asc': 'Oldest first'},
                  onChanged: (value) => setState(() => _order = value),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Text('Estimated raw rows in selected range: $estimated. Table rendering and export use the selected row limit. For full 7/30/90-day raw exports, use backend/server-side export in the next backend phase.', style: const TextStyle(color: Color(0xFF5B6775))),
            const SizedBox(height: 12),
            _signalSelector(context),
            const SizedBox(height: 14),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                FilledButton.icon(
                  onPressed: _historyLoading ? null : _loadHistory,
                  icon: const Icon(Icons.table_rows_rounded),
                  label: Text(_historyLoading ? 'Loading...' : 'Load history'),
                ),
                OutlinedButton.icon(
                  onPressed: _historyItems.isEmpty || _exporting ? null : _exportCsv,
                  icon: const Icon(Icons.download_rounded),
                  label: const Text('Download CSV'),
                ),
                OutlinedButton.icon(
                  onPressed: _historyItems.isEmpty || _exporting ? null : _exportXlsx,
                  icon: const Icon(Icons.table_chart_rounded),
                  label: Text(_exporting ? 'Exporting...' : 'Download Excel'),
                ),
                OutlinedButton.icon(
                  onPressed: () {
                    setState(() {
                      _historyItems = const [];
                      _exportMessage = null;
                    });
                  },
                  icon: const Icon(Icons.clear_rounded),
                  label: const Text('Clear table'),
                ),
              ],
            ),
            if (_exportMessage != null) ...[
              const SizedBox(height: 10),
              Text(_exportMessage!, style: const TextStyle(color: Color(0xFF276749), fontWeight: FontWeight.w600)),
            ],
          ],
        ),
      ),
    );
  }

  Widget _dropdown({
    required String label,
    required String value,
    required Map<String, String> items,
    required ValueChanged<String> onChanged,
  }) {
    return SizedBox(
      width: 190,
      child: DropdownButtonFormField<String>(
        value: value,
        decoration: InputDecoration(labelText: label, border: const OutlineInputBorder()),
        items: items.entries
            .map((entry) => DropdownMenuItem<String>(
                  value: entry.key,
                  child: Text(entry.value),
                ))
            .toList(),
        onChanged: (next) {
          if (next != null) onChanged(next);
        },
      ),
    );
  }

  Widget _signalSelector(BuildContext context) {
    final options = _availableSignals;
    final selectedCount = options.where((e) => _selectedSignalKeys.contains(e.key)).length;
    final preview = _selectedSignals.take(6).map((e) => e.label).join(', ');

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFF8FAFD),
        border: Border.all(color: const Color(0xFFDDE5EF)),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Parameter selection ($selectedCount selected)',
                      style: const TextStyle(fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      preview.isEmpty ? 'No parameter selected. Default critical parameters will be used.' : preview,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(color: Color(0xFF5B6775)),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              OutlinedButton.icon(
                onPressed: options.isEmpty ? null : _openSignalSelectionDialog,
                icon: const Icon(Icons.tune_rounded),
                label: const Text('Choose parameters'),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              OutlinedButton(
                onPressed: options.isEmpty
                    ? null
                    : () => setState(() {
                          _selectedSignalKeys
                            ..clear()
                            ..addAll(options.map((e) => e.key));
                        }),
                child: const Text('Select all shown'),
              ),
              OutlinedButton(
                onPressed: () => setState(() => _selectedSignalKeys.clear()),
                child: const Text('Clear'),
              ),
              OutlinedButton(
                onPressed: () => setState(() {
                  _selectedSignalKeys
                    ..clear()
                    ..addAll(_defaultSelectedKeys);
                }),
                child: const Text('Default critical'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Future<void> _openSignalSelectionDialog() async {
    final options = _availableSignals;
    final temp = Set<String>.from(_selectedSignalKeys);

    await showDialog<void>(
      context: context,
      builder: (dialogContext) {
        return StatefulBuilder(
          builder: (context, setDialogState) {
            final pcsOptions = options.where((e) => e.assetType == 'pcs').toList();
            final bmsOptions = options.where((e) => e.assetType == 'bms').toList();
            final selectedCount = options.where((e) => temp.contains(e.key)).length;

            return AlertDialog(
              title: Text('Select historian parameters ($selectedCount)'),
              content: SizedBox(
                width: 720,
                height: 520,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Select the columns that should be visible in the historian table and exported in CSV/Excel.',
                      style: TextStyle(color: Color(0xFF5B6775)),
                    ),
                    const SizedBox(height: 12),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        OutlinedButton(
                          onPressed: () => setDialogState(() {
                            temp
                              ..clear()
                              ..addAll(options.map((e) => e.key));
                          }),
                          child: const Text('Select all'),
                        ),
                        OutlinedButton(
                          onPressed: () => setDialogState(() => temp.clear()),
                          child: const Text('Clear all'),
                        ),
                        OutlinedButton(
                          onPressed: () => setDialogState(() {
                            temp
                              ..clear()
                              ..addAll(_defaultSelectedKeys);
                          }),
                          child: const Text('Default critical'),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Expanded(
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(child: _signalChecklist('PCS', pcsOptions, temp, setDialogState)),
                          const SizedBox(width: 16),
                          Expanded(child: _signalChecklist('BMS', bmsOptions, temp, setDialogState)),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.of(dialogContext).pop(),
                  child: const Text('Cancel'),
                ),
                FilledButton(
                  onPressed: () {
                    setState(() {
                      _selectedSignalKeys
                        ..clear()
                        ..addAll(temp);
                    });
                    Navigator.of(dialogContext).pop();
                  },
                  child: const Text('Apply'),
                ),
              ],
            );
          },
        );
      },
    );
  }

  Widget _signalChecklist(
    String title,
    List<_SignalOption> options,
    Set<String> selectedKeys,
    StateSetter setDialogState,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
        const SizedBox(height: 8),
        Expanded(
          child: DecoratedBox(
            decoration: BoxDecoration(
              border: Border.all(color: const Color(0xFFDDE5EF)),
              borderRadius: BorderRadius.circular(10),
            ),
            child: ListView.builder(
              itemCount: options.length,
              itemBuilder: (context, index) {
                final option = options[index];
                final checked = selectedKeys.contains(option.key);
                return CheckboxListTile(
                  dense: true,
                  value: checked,
                  controlAffinity: ListTileControlAffinity.leading,
                  title: Text(option.name, style: const TextStyle(fontSize: 13)),
                  onChanged: (value) {
                    setDialogState(() {
                      if (value == true) {
                        selectedKeys.add(option.key);
                      } else {
                        selectedKeys.remove(option.key);
                      }
                    });
                  },
                );
              },
            ),
          ),
        ),
      ],
    );
  }

  Widget _historyTableCard(BuildContext context) {
    final rows = _historyItems.take(_maxTableRows).toList();
    final signals = _selectedSignals;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text('History Table', style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700)),
                ),
                if (_historyLoading) const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
                if (_exporting) const Padding(
                  padding: EdgeInsets.only(left: 12),
                  child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text('Rows loaded: ${_historyItems.length}. Columns shown: ${signals.length}. Export downloads exactly the currently loaded, filtered table.', style: const TextStyle(color: Color(0xFF5B6775))),
            const SizedBox(height: 14),
            if (rows.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 16),
                child: Text('No history loaded yet. Choose filters and click Load history.'),
              )
            else
              Scrollbar(
                thumbVisibility: true,
                child: SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: DataTable(
                    headingRowColor: WidgetStateProperty.all(const Color(0xFFF1F5FA)),
                    columns: [
                      const DataColumn(label: Text('Time')),
                      const DataColumn(label: Text('BESS')),
                      const DataColumn(label: Text('Quality')),
                      const DataColumn(label: Text('Age ms')),
                      ...signals.map((signal) => DataColumn(label: Text(signal.label))),
                    ],
                    rows: rows.map((item) => _dataRow(item, signals)).toList(),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  DataRow _dataRow(Map<String, dynamic> item, List<_SignalOption> signals) {
    final pcs = _mapValue(item['pcs_values']);
    final bms = _mapValue(item['bms_values']);
    return DataRow(
      cells: [
        DataCell(Text(_shortTime(item['timestamp_utc']))),
        DataCell(Text(_text(item['bess_id']))),
        DataCell(Text(_text(item['quality']))),
        DataCell(Text(_text(item['max_data_age_ms']))),
        ...signals.map((signal) {
          final source = signal.assetType == 'pcs' ? pcs : bms;
          return DataCell(Text(_valueText(source[signal.name])));
        }),
      ],
    );
  }


  Object? _rawCellValue(dynamic raw) {
    if (raw == null) return null;
    if (raw is Map) return _rawCellValue(raw['value']);
    if (raw is num || raw is bool) return raw;
    return raw.toString();
  }

  String _localTimestamp(dynamic value) {
    if (value == null) return '';
    try {
      return DateTime.parse(value.toString()).toLocal().toIso8601String();
    } catch (_) {
      return value.toString();
    }
  }

  String _fileStamp(DateTime value) {
    final dt = value.toLocal();
    final two = (int v) => v.toString().padLeft(2, '0');
    return '${dt.year}${two(dt.month)}${two(dt.day)}_${two(dt.hour)}${two(dt.minute)}${two(dt.second)}';
  }

  void _showSnack(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), duration: const Duration(seconds: 4)),
    );
  }

  Map<String, dynamic> _mapValue(dynamic value) {
    if (value is Map<String, dynamic>) return value;
    if (value is Map) return value.map((key, val) => MapEntry(key.toString(), val));
    return <String, dynamic>{};
  }

  String _valueText(dynamic raw) {
    if (raw == null) return '--';
    if (raw is Map) {
      final value = raw['value'];
      if (value == null) return '--';
      return _valueText(value);
    }
    if (raw is num) {
      final abs = raw.abs();
      if (abs >= 1000) return raw.toStringAsFixed(0);
      if (abs >= 100) return raw.toStringAsFixed(1);
      return raw.toStringAsFixed(2).replaceFirst(RegExp(r'\.00$'), '');
    }
    return raw.toString();
  }

  String _text(dynamic value) => value == null ? '--' : value.toString();

  String _boolLabel(dynamic value) {
    if (value == true) return 'Running';
    if (value == false) return 'Stopped';
    return _text(value);
  }

  String _shortTime(dynamic value) {
    if (value == null) return '--';
    final text = value.toString();
    try {
      final dt = DateTime.parse(text).toLocal();
      final two = (int v) => v.toString().padLeft(2, '0');
      return '${two(dt.hour)}:${two(dt.minute)}:${two(dt.second)}';
    } catch (_) {
      return text;
    }
  }
}
