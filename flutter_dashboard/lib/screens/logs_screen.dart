import 'dart:async';

import 'package:flutter/material.dart';

import '../config/app_config.dart';
import '../features/logs/controllers/log_filter_builder.dart';
import '../features/logs/log_field_catalog.dart';
import '../features/logs/widgets/widgets.dart';
import '../models/log_filter_model.dart';
import '../models/log_models.dart';
import '../repositories/log_repository.dart';
import '../services/log_api_service.dart';

class LogsScreen extends StatefulWidget {
  final String initialGatewayIp;

  const LogsScreen({
    super.key,
    required this.initialGatewayIp,
  });

  @override
  State<LogsScreen> createState() => _LogsScreenState();
}

class _LogsScreenState extends State<LogsScreen> {
  late final TextEditingController _gatewayIpController;
  late final TextEditingController _dateController;
  late final TextEditingController _startTimeController;
  late final TextEditingController _endTimeController;
  late final TextEditingController _searchController;

  int _limit = 100;
  int _activeTabIndex = 0;
  bool _loading = false;
  bool _showFilters = true;
  bool _useSelectedTelemetryFields = false;

  String _statusMessage = 'Ready to fetch i.MX93 logs';

  String _selectedAssetId = AppConfig.chillerAssetId;

  String _modbusStatusFilter = 'All';
  String _loggerStatusFilter = 'All';

  String _pcsVendorFilter = 'All';
  String _pcsCommStatusFilter = 'All';
  String _pcsOperatingStatusFilter = 'All';
  String _pcsFaultStatusFilter = 'All';

  String _eventTypeFilter = 'All';
  String _eventStatusFilter = 'All';
  String _pcsCommandFilter = 'All';
  String _errorTypeFilter = 'All';

  StorageStatus? _storageStatus;
  LogFilesResponse? _logFiles;
  LogApiResponse? _telemetryLogs;
  LogApiResponse? _eventLogs;
  LogApiResponse? _errorLogs;
  MetadataResponse? _metadata;
  LogAssetsResponse? _assetsResponse;

  final List<String> _chillerTelemetryFieldOrder = const [
    'timestamp',
    'sequence_no',
    'gateway_id',
    'asset_id',
    'system_on_off',
    'control_mode',
    'set_temperature',
    'outlet_water_temp',
    'return_water_temp',
    'outlet_water_pressure',
    'return_water_pressure',
    'ambient_temp',
    'water_pump_status',
    'compressor_1_status',
    'compressor_2_status',
    'electric_heater_status',
    'condensate_fan_status',
    'modbus_status',
    'logger_status',
  ];

  final List<String> _pcsTelemetryFieldOrder = const [
    'timestamp',
    'sequence_no',
    'gateway_id',
    'asset_id',
    'vendor',
    'comm_status',
    'active_power_kw',
    'reactive_power_kvar',
    'apparent_power_kva',
    'power_factor',
    'frequency_hz',
    'battery_voltage_v',
    'battery_current_a',
    'dc_power_kw',
    'bus_voltage_v',
    'phase_a_voltage_v',
    'phase_b_voltage_v',
    'phase_c_voltage_v',
    'phase_a_current_a',
    'phase_b_current_a',
    'phase_c_current_a',
    'operating_status',
    'grid_offgrid_status',
    'operating_status_raw',
    'grid_offgrid_status_raw',
    'fault_status',
    'detailed_fault_status',
    'fault_count',
    'hardware_fault_word_1_raw',
    'hardware_fault_word_2_raw',
    'grid_fault_word_raw',
    'bus_fault_word_raw',
    'ac_capacitor_fault_word_raw',
    'system_fault_word_raw',
    'switch_fault_word_raw',
    'other_fault_word_raw',
    'active_faults',
    'fault_words_read_error',
    'igbt_temperature_c',
    'ambient_temperature_c',
    'inductance_temperature_c',
    'error',
    'logger_status',
  ];

  late Set<String> _selectedTelemetryFields;

  final List<String> _bmsTelemetryFieldOrder = const [
    'timestamp',
    'sequence_no',
    'gateway_id',
    'asset_id',
    'comm_status',
    'soc_percent',
    'soh_percent',
    'rack_voltage_v',
    'rack_current_a',
    'power_kw',
    'max_cell_voltage_mv',
    'min_cell_voltage_mv',
    'cell_voltage_diff_mv',
    'max_cell_temp_c',
    'min_cell_temp_c',
    'avg_temp_c',
    'insulation_resistance_kohm',
    'positive_insulation_resistance_kohm',
    'negative_insulation_resistance_kohm',
    'precharge_stage',
    'bcu_state',
    'current_state',
    'alarm_count',
    'active_alarms',
    'logger_status',
  ];

  bool get _isPcsAsset => LogFieldCatalog.isPcsAsset(_selectedAssetId);
  bool get _isBmsAsset => LogFieldCatalog.isBmsAsset(_selectedAssetId);

  List<String> get _activeTelemetryFieldOrder =>
      LogFieldCatalog.telemetryFieldOrder(_selectedAssetId);

  List<String> get _activeTelemetryPreferredColumns =>
      LogFieldCatalog.telemetryFieldOrder(_selectedAssetId);

  List<String> get _activeEventPreferredColumns =>
      LogFieldCatalog.eventPreferredColumns(_selectedAssetId);

  List<String> get _activeErrorPreferredColumns =>
      LogFieldCatalog.errorPreferredColumns;

  @override
  void initState() {
    super.initState();

    _gatewayIpController = TextEditingController(
      text: widget.initialGatewayIp.isNotEmpty
          ? widget.initialGatewayIp
          : AppConfig.defaultGatewayIp,
    );

    _dateController = TextEditingController(text: _todayDate());
    _startTimeController = TextEditingController();
    _endTimeController = TextEditingController();
    _searchController = TextEditingController();

    _selectedTelemetryFields = _defaultTelemetryFieldsForAsset(_selectedAssetId);
  }

  @override
  void dispose() {
    _gatewayIpController.dispose();
    _dateController.dispose();
    _startTimeController.dispose();
    _endTimeController.dispose();
    _searchController.dispose();
    super.dispose();
  }

  Set<String> _defaultTelemetryFieldsForAsset(String assetId) =>
      LogFieldCatalog.defaultTelemetryFields(assetId);

  String _todayDate() {
    final now = DateTime.now();

    return '${now.year.toString().padLeft(4, '0')}-'
        '${now.month.toString().padLeft(2, '0')}-'
        '${now.day.toString().padLeft(2, '0')}';
  }

  LogRepository _api() {
    return LogRepository(
      api: LogApiService(
        gatewayIp: _gatewayIpController.text.trim(),
        port: AppConfig.logHttpPort,
        timeout: AppConfig.httpTimeout,
      ),
    );
  }

  String? _filterText(String text) => LogFilterBuilder.text(text);

  String? _filterDropdown(String value) => LogFilterBuilder.dropdown(value);

  String? _telemetryFieldsCsv() {
    if (!_useSelectedTelemetryFields) return null;
    if (_selectedTelemetryFields.isEmpty) return null;

    final ordered = _activeTelemetryFieldOrder.where(
      _selectedTelemetryFields.contains,
    );

    return ordered.join(',');
  }

  String _dateFromFileName(String fileName) {
    return fileName.replaceAll('.csv', '');
  }

  Future<void> _checkHealth() async {
    setState(() {
      _loading = true;
      _statusMessage = 'Checking HTTP Log API health...';
    });

    try {
      final response = await _api().fetchHealth();

      setState(() {
        _statusMessage =
            'HTTP Log API OK: ${response['server'] ?? 'server'} at ${response['timestamp'] ?? '--'}';
      });
    } catch (e) {
      setState(() {
        _statusMessage = 'Health check failed: $e';
      });
    } finally {
      setState(() {
        _loading = false;
      });
    }
  }

  Future<String> _loadStorageAndResolveDate(LogRepository api) async {
    final assetsFuture = api.fetchAssets().catchError((_) {
      return LogAssetsResponse(
        status: 'fallback',
        assets: AppConfig.supportedLogAssets,
        raw: const {},
      );
    });

    final results = await Future.wait([
      assetsFuture,
      api.fetchStorageStatus(assetId: _selectedAssetId),
      api.fetchLogFiles(assetId: _selectedAssetId),
    ]);

    _assetsResponse = results[0] as LogAssetsResponse;
    final storage = results[1] as StorageStatus;
    final files = results[2] as LogFilesResponse;

    var selectedDate = _dateController.text.trim();

    final availableDates = files.files.map(_dateFromFileName).toList();

    if (!availableDates.contains(selectedDate) && availableDates.isNotEmpty) {
      selectedDate = availableDates.first;
      _dateController.text = selectedDate;
    }

    _storageStatus = storage;
    _logFiles = files;

    return selectedDate;
  }

  LogFilterModel _telemetryFilter(String effectiveDate) {
    return LogFilterBuilder.telemetry(
      assetId: _selectedAssetId,
      date: effectiveDate,
      limit: _limit,
      startTime: _filterText(_startTimeController.text),
      endTime: _filterText(_endTimeController.text),
      fields: _telemetryFieldsCsv(),
      modbusStatus: _isPcsAsset ? null : _filterDropdown(_modbusStatusFilter),
      loggerStatus: _filterDropdown(_loggerStatusFilter),
      vendor: _isPcsAsset ? _filterDropdown(_pcsVendorFilter) : null,
      commStatus: (_isPcsAsset || _isBmsAsset)
          ? _filterDropdown(_pcsCommStatusFilter)
          : null,
      operatingStatus: _isPcsAsset
          ? _filterDropdown(_pcsOperatingStatusFilter)
          : null,
      faultStatus: _isPcsAsset ? _filterDropdown(_pcsFaultStatusFilter) : null,
      search: _filterText(_searchController.text),
    );
  }

  LogFilterModel _eventFilter(String effectiveDate) {
    return LogFilterBuilder.events(
      assetId: _selectedAssetId,
      date: effectiveDate,
      limit: _limit,
      startTime: _filterText(_startTimeController.text),
      endTime: _filterText(_endTimeController.text),
      eventType: _filterDropdown(_eventTypeFilter),
      status: _filterDropdown(_eventStatusFilter),
      command: (_isPcsAsset || _isBmsAsset)
          ? _filterDropdown(_pcsCommandFilter)
          : null,
      vendor: _isPcsAsset ? _filterDropdown(_pcsVendorFilter) : null,
      search: _filterText(_searchController.text),
    );
  }

  LogFilterModel _errorFilter(String effectiveDate) {
    return LogFilterBuilder.errors(
      assetId: _selectedAssetId,
      date: effectiveDate,
      limit: _limit,
      startTime: _filterText(_startTimeController.text),
      endTime: _filterText(_endTimeController.text),
      errorType: _filterDropdown(_errorTypeFilter),
      search: _filterText(_searchController.text),
    );
  }

  Future<void> _refreshAll() async {
    setState(() {
      _loading = true;
      _statusMessage = 'Fetching $_selectedAssetId logs from i.MX93...';
    });

    try {
      final api = _api();

      final effectiveDate = await _loadStorageAndResolveDate(api);

      final results = await Future.wait([
        api.fetchTelemetryLogs(
          _telemetryFilter(effectiveDate),
        ),
        api.fetchEventLogs(
          _eventFilter(effectiveDate),
        ),
        api.fetchErrorLogs(
          _errorFilter(effectiveDate),
        ),
        api.fetchMetadata(assetId: _selectedAssetId),
      ]);

      setState(() {
        _telemetryLogs = results[0] as LogApiResponse;
        _eventLogs = results[1] as LogApiResponse;
        _errorLogs = results[2] as LogApiResponse;
        _metadata = results[3] as MetadataResponse;

        _statusMessage = '$_selectedAssetId logs refreshed successfully';
      });
    } catch (e) {
      setState(() {
        _statusMessage = 'Log refresh failed: $e';
      });
    } finally {
      setState(() {
        _loading = false;
      });
    }
  }

  Future<void> _fetchTelemetryOnly() async {
    setState(() {
      _loading = true;
      _statusMessage = 'Fetching $_selectedAssetId telemetry logs...';
    });

    try {
      final api = _api();
      final effectiveDate = await _loadStorageAndResolveDate(api);

      final logs = await api.fetchTelemetryLogs(
        _telemetryFilter(effectiveDate),
      );

      setState(() {
        _telemetryLogs = logs;
        _statusMessage = '$_selectedAssetId telemetry logs refreshed';
      });
    } catch (e) {
      setState(() {
        _statusMessage = 'Telemetry log fetch failed: $e';
      });
    } finally {
      setState(() {
        _loading = false;
      });
    }
  }

  void _clearFilters() {
    setState(() {
      _startTimeController.clear();
      _endTimeController.clear();
      _searchController.clear();

      _modbusStatusFilter = 'All';
      _loggerStatusFilter = 'All';
      _pcsVendorFilter = 'All';
      _pcsCommStatusFilter = 'All';
      _pcsOperatingStatusFilter = 'All';
      _pcsFaultStatusFilter = 'All';
      _eventTypeFilter = 'All';
      _eventStatusFilter = 'All';
      _pcsCommandFilter = 'All';
      _errorTypeFilter = 'All';

      _useSelectedTelemetryFields = false;
      _selectedTelemetryFields = _defaultTelemetryFieldsForAsset(_selectedAssetId);
    });
  }

  void _onAssetChanged(String assetId) {
    setState(() {
      _selectedAssetId = assetId;
      _telemetryLogs = null;
      _eventLogs = null;
      _errorLogs = null;
      _storageStatus = null;
      _logFiles = null;
      _metadata = null;
      _selectedTelemetryFields = _defaultTelemetryFieldsForAsset(assetId);
      _useSelectedTelemetryFields = false;

      _modbusStatusFilter = 'All';
      _pcsVendorFilter = 'All';
      _pcsCommStatusFilter = 'All';
      _pcsOperatingStatusFilter = 'All';
      _pcsFaultStatusFilter = 'All';
      _eventTypeFilter = 'All';
      _pcsCommandFilter = 'All';
      _errorTypeFilter = 'All';

      _statusMessage = 'Selected asset: $assetId. Press Refresh Logs.';
    });
  }

  String _value(dynamic value) {
    if (value == null) return '--';

    final text = value.toString();

    if (text.isEmpty) return '--';

    return text;
  }

  List<String> _assetOptions() {
    final fromApi = _assetsResponse?.assets ?? const <String>[];
    final merged = <String>{
      ...AppConfig.supportedLogAssets,
      ...fromApi,
    }.toList();

    if (!merged.contains(_selectedAssetId)) {
      merged.add(_selectedAssetId);
    }

    return merged;
  }

  @override
  Widget build(BuildContext context) {
    final downloadUrl = _api().telemetryCsvDownloadUrl(
      assetId: _selectedAssetId,
      date: _dateController.text.trim(),
    );

    return DefaultTabController(
      length: 4,
      child: Scaffold(
        appBar: AppBar(
          title: Text('EMS Logs & History - $_selectedAssetId'),
          actions: [
            Padding(
              padding: const EdgeInsets.only(right: 16),
              child: Center(
                child: _loading
                    ? const SizedBox(
                        width: 22,
                        height: 22,
                        child: CircularProgressIndicator(strokeWidth: 2.5),
                      )
                    : const Icon(Icons.history),
              ),
            ),
          ],
          bottom: TabBar(
            onTap: (index) {
              setState(() {
                _activeTabIndex = index;
              });
            },
            tabs: const [
              Tab(
                icon: Icon(Icons.monitor_heart),
                text: 'Telemetry',
              ),
              Tab(
                icon: Icon(Icons.event_note),
                text: 'Events',
              ),
              Tab(
                icon: Icon(Icons.error_outline),
                text: 'Errors',
              ),
              Tab(
                icon: Icon(Icons.storage),
                text: 'Storage',
              ),
            ],
          ),
        ),
        body: Column(
          children: [
            _buildControlPanel(downloadUrl),
            Expanded(
              child: TabBarView(
                children: [
                  _buildTelemetryTab(),
                  _buildEventsTab(),
                  _buildErrorsTab(),
                  _buildStorageTab(),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildControlPanel(String downloadUrl) {
    return Card(
      margin: const EdgeInsets.all(14),
      elevation: 1,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: 12,
              runSpacing: 12,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                SizedBox(
                  width: 230,
                  child: TextField(
                    controller: _gatewayIpController,
                    decoration: const InputDecoration(
                      labelText: 'i.MX93 Gateway IP',
                      border: OutlineInputBorder(),
                      prefixIcon: Icon(Icons.router),
                    ),
                  ),
                ),
                SizedBox(
                  width: 175,
                  child: DropdownButtonFormField<String>(
                    initialValue: _selectedAssetId,
                    decoration: const InputDecoration(
                      labelText: 'Asset',
                      border: OutlineInputBorder(),
                      prefixIcon: Icon(Icons.devices_other),
                    ),
                    items: _assetOptions().map((assetId) {
                      return DropdownMenuItem(
                        value: assetId,
                        child: Text(assetId),
                      );
                    }).toList(),
                    onChanged: (value) {
                      if (value == null) return;
                      _onAssetChanged(value);
                    },
                  ),
                ),
                SizedBox(
                  width: 180,
                  child: TextField(
                    controller: _dateController,
                    decoration: const InputDecoration(
                      labelText: 'Log Date',
                      hintText: 'YYYY-MM-DD',
                      border: OutlineInputBorder(),
                      prefixIcon: Icon(Icons.calendar_month),
                    ),
                  ),
                ),
                SizedBox(
                  width: 145,
                  child: DropdownButtonFormField<int>(
                    initialValue: _limit,
                    decoration: const InputDecoration(
                      labelText: 'Rows',
                      border: OutlineInputBorder(),
                    ),
                    items: const [
                      DropdownMenuItem(value: 20, child: Text('20')),
                      DropdownMenuItem(value: 50, child: Text('50')),
                      DropdownMenuItem(value: 100, child: Text('100')),
                      DropdownMenuItem(value: 500, child: Text('500')),
                    ],
                    onChanged: (value) {
                      if (value == null) return;

                      setState(() {
                        _limit = value;
                      });
                    },
                  ),
                ),
                FilledButton.icon(
                  onPressed: _loading ? null : _checkHealth,
                  icon: const Icon(Icons.health_and_safety),
                  label: const Text('Check API'),
                ),
                FilledButton.icon(
                  onPressed: _loading ? null : _refreshAll,
                  icon: const Icon(Icons.refresh),
                  label: const Text('Refresh Logs'),
                ),
                FilledButton.tonalIcon(
                  onPressed: _loading ? null : _fetchTelemetryOnly,
                  icon: const Icon(Icons.monitor_heart),
                  label: const Text('Telemetry Only'),
                ),
                OutlinedButton.icon(
                  onPressed: _loading ? null : _clearFilters,
                  icon: const Icon(Icons.filter_alt_off),
                  label: const Text('Clear Filters'),
                ),
                SizedBox(
                  width: 210,
                  child: SwitchListTile(
                    dense: true,
                    title: const Text('Show Filters'),
                    value: _showFilters,
                    onChanged: (value) {
                      setState(() {
                        _showFilters = value;
                      });
                    },
                  ),
                ),
              ],
            ),
            if (_showFilters) ...[
              const SizedBox(height: 12),
              _buildAdvancedFilters(),
            ],
            const SizedBox(height: 10),
            SelectableText(
              _statusMessage,
              style: TextStyle(
                color: _statusMessage.toLowerCase().contains('failed')
                    ? Colors.red
                    : Colors.black87,
                fontWeight: FontWeight.w500,
              ),
            ),
            const SizedBox(height: 6),
            SelectableText(
              'CSV download URL: $downloadUrl',
              style: const TextStyle(
                fontSize: 12,
                color: Colors.black54,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAdvancedFilters() {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        SizedBox(
          width: 150,
          child: TextField(
            controller: _startTimeController,
            decoration: const InputDecoration(
              labelText: 'Start Time',
              hintText: 'HH:MM:SS',
              border: OutlineInputBorder(),
              prefixIcon: Icon(Icons.access_time),
            ),
          ),
        ),
        SizedBox(
          width: 150,
          child: TextField(
            controller: _endTimeController,
            decoration: const InputDecoration(
              labelText: 'End Time',
              hintText: 'HH:MM:SS',
              border: OutlineInputBorder(),
              prefixIcon: Icon(Icons.access_time_filled),
            ),
          ),
        ),
        SizedBox(
          width: 260,
          child: TextField(
            controller: _searchController,
            decoration: InputDecoration(
              labelText: 'Search',
              hintText: _isPcsAsset
                  ? 'njoy, active power, offline...'
                  : 'temperature, mode, error...',
              border: const OutlineInputBorder(),
              prefixIcon: const Icon(Icons.search),
            ),
          ),
        ),
        if (_activeTabIndex == 0) ..._buildTelemetryFilterControls(),
        if (_activeTabIndex == 1) ..._buildEventFilterControls(),
        if (_activeTabIndex == 2) ..._buildErrorFilterControls(),
      ],
    );
  }

  List<Widget> _buildTelemetryFilterControls() {
    final controls = <Widget>[
      SizedBox(
        width: 160,
        child: DropdownButtonFormField<String>(
          initialValue: _loggerStatusFilter,
          decoration: const InputDecoration(
            labelText: 'Logger Status',
            border: OutlineInputBorder(),
          ),
          items: const [
            DropdownMenuItem(value: 'All', child: Text('All')),
            DropdownMenuItem(value: 'ok', child: Text('ok')),
            DropdownMenuItem(value: 'telemetry_write_failed', child: Text('write failed')),
          ],
          onChanged: (value) {
            if (value == null) return;

            setState(() {
              _loggerStatusFilter = value;
            });
          },
        ),
      ),
      FilterChip(
        label: const Text('Selective Fields'),
        selected: _useSelectedTelemetryFields,
        onSelected: (value) {
          setState(() {
            _useSelectedTelemetryFields = value;
          });
        },
      ),
      OutlinedButton.icon(
        onPressed: _showTelemetryFieldDialog,
        icon: const Icon(Icons.view_column),
        label: Text(
          'Fields (${_selectedTelemetryFields.length})',
        ),
      ),
    ];

    if (_isPcsAsset) {
      controls.insertAll(0, [
        SizedBox(
          width: 160,
          child: DropdownButtonFormField<String>(
            initialValue: _pcsVendorFilter,
            decoration: const InputDecoration(
              labelText: 'PCS Vendor',
              border: OutlineInputBorder(),
            ),
            items: const [
              DropdownMenuItem(value: 'All', child: Text('All')),
              DropdownMenuItem(value: 'njoy', child: Text('njoy')),
              DropdownMenuItem(value: 'njoy_125kw', child: Text('njoy_125kw')),
              DropdownMenuItem(value: 'inpower', child: Text('inpower')),
              DropdownMenuItem(value: 'inpower_125kw', child: Text('inpower_125kw')),
            ],
            onChanged: (value) {
              if (value == null) return;
              setState(() => _pcsVendorFilter = value);
            },
          ),
        ),
        SizedBox(
          width: 160,
          child: DropdownButtonFormField<String>(
            initialValue: _pcsCommStatusFilter,
            decoration: const InputDecoration(
              labelText: 'PCS Comm',
              border: OutlineInputBorder(),
            ),
            items: const [
              DropdownMenuItem(value: 'All', child: Text('All')),
              DropdownMenuItem(value: 'online', child: Text('online')),
              DropdownMenuItem(value: 'offline', child: Text('offline')),
            ],
            onChanged: (value) {
              if (value == null) return;
              setState(() => _pcsCommStatusFilter = value);
            },
          ),
        ),
        SizedBox(
          width: 210,
          child: DropdownButtonFormField<String>(
            initialValue: _pcsOperatingStatusFilter,
            decoration: const InputDecoration(
              labelText: 'Operating Status',
              border: OutlineInputBorder(),
            ),
            items: const [
              DropdownMenuItem(value: 'All', child: Text('All')),
              DropdownMenuItem(value: 'running_grid_connected', child: Text('running_grid_connected')),
              DropdownMenuItem(value: 'grid_connected_operation', child: Text('grid_connected_operation')),
              DropdownMenuItem(value: 'operation', child: Text('operation')),
              DropdownMenuItem(value: 'charging', child: Text('charging')),
              DropdownMenuItem(value: 'discharging', child: Text('discharging')),
              DropdownMenuItem(value: 'standby', child: Text('standby')),
              DropdownMenuItem(value: 'fault', child: Text('fault')),
            ],
            onChanged: (value) {
              if (value == null) return;
              setState(() => _pcsOperatingStatusFilter = value);
            },
          ),
        ),
        SizedBox(
          width: 150,
          child: DropdownButtonFormField<String>(
            initialValue: _pcsFaultStatusFilter,
            decoration: const InputDecoration(
              labelText: 'PCS Fault',
              border: OutlineInputBorder(),
            ),
            items: const [
              DropdownMenuItem(value: 'All', child: Text('All')),
              DropdownMenuItem(value: 'True', child: Text('True')),
              DropdownMenuItem(value: 'False', child: Text('False')),
              DropdownMenuItem(value: 'true', child: Text('true')),
              DropdownMenuItem(value: 'false', child: Text('false')),
            ],
            onChanged: (value) {
              if (value == null) return;
              setState(() => _pcsFaultStatusFilter = value);
            },
          ),
        ),
      ]);
    } else {
      controls.insert(
        0,
        SizedBox(
          width: 160,
          child: DropdownButtonFormField<String>(
            initialValue: _modbusStatusFilter,
            decoration: const InputDecoration(
              labelText: 'Modbus Status',
              border: OutlineInputBorder(),
            ),
            items: const [
              DropdownMenuItem(value: 'All', child: Text('All')),
              DropdownMenuItem(value: 'online', child: Text('online')),
              DropdownMenuItem(value: 'OK', child: Text('OK')),
              DropdownMenuItem(value: 'failed', child: Text('failed')),
              DropdownMenuItem(value: 'error', child: Text('error')),
            ],
            onChanged: (value) {
              if (value == null) return;

              setState(() {
                _modbusStatusFilter = value;
              });
            },
          ),
        ),
      );
    }

    return controls;
  }

  List<Widget> _buildEventFilterControls() {
    return [
      SizedBox(
        width: 250,
        child: DropdownButtonFormField<String>(
          initialValue: _eventTypeFilter,
          decoration: const InputDecoration(
            labelText: 'Event Type',
            border: OutlineInputBorder(),
          ),
          items: [
            const DropdownMenuItem(value: 'All', child: Text('All')),
            if (!_isPcsAsset) ...const [
              DropdownMenuItem(value: 'SET_TEMPERATURE_WRITE', child: Text('SET_TEMP')),
              DropdownMenuItem(value: 'CONTROL_MODE_WRITE', child: Text('SET_MODE')),
              DropdownMenuItem(value: 'SYSTEM_ON_OFF_WRITE', child: Text('ON/OFF')),
              DropdownMenuItem(value: 'STORAGE_LOGGER_STARTED', child: Text('LOGGER START')),
              DropdownMenuItem(value: 'STORAGE_LOGGER_STOPPED', child: Text('LOGGER STOP')),
            ],
            if (_isPcsAsset) ...const [
              DropdownMenuItem(value: 'PCS_SERVICE_STARTED', child: Text('PCS STARTED')),
              DropdownMenuItem(value: 'PCS_SERVICE_STOPPED', child: Text('PCS STOPPED')),
              DropdownMenuItem(value: 'PCS_COMM_STATUS_CHANGED', child: Text('COMM STATUS')),
              DropdownMenuItem(value: 'PCS_POWER_ON_WRITE', child: Text('POWER ON')),
              DropdownMenuItem(value: 'PCS_POWER_OFF_WRITE', child: Text('POWER OFF')),
              DropdownMenuItem(value: 'PCS_ACTIVE_POWER_WRITE', child: Text('ACTIVE POWER')),
              DropdownMenuItem(value: 'PCS_REACTIVE_POWER_WRITE', child: Text('REACTIVE POWER')),
              DropdownMenuItem(value: 'PCS_FAULT_RESET_WRITE', child: Text('FAULT RESET')),
              DropdownMenuItem(value: 'PCS_HEARTBEAT_WRITE', child: Text('HEARTBEAT')),
            ],
          ],
          onChanged: (value) {
            if (value == null) return;

            setState(() {
              _eventTypeFilter = value;
            });
          },
        ),
      ),
      if (_isPcsAsset)
        SizedBox(
          width: 210,
          child: DropdownButtonFormField<String>(
            initialValue: _pcsCommandFilter,
            decoration: const InputDecoration(
              labelText: 'PCS Command',
              border: OutlineInputBorder(),
            ),
            items: const [
              DropdownMenuItem(value: 'All', child: Text('All')),
              DropdownMenuItem(value: 'power_on', child: Text('power_on')),
              DropdownMenuItem(value: 'power_off', child: Text('power_off')),
              DropdownMenuItem(value: 'set_active_power_kw', child: Text('set_active_power_kw')),
              DropdownMenuItem(value: 'set_reactive_power_kvar', child: Text('set_reactive_power_kvar')),
              DropdownMenuItem(value: 'reset_fault', child: Text('reset_fault')),
              DropdownMenuItem(value: 'heartbeat', child: Text('heartbeat')),
              DropdownMenuItem(value: 'standby', child: Text('standby')),
            ],
            onChanged: (value) {
              if (value == null) return;
              setState(() => _pcsCommandFilter = value);
            },
          ),
        ),
      SizedBox(
        width: 150,
        child: DropdownButtonFormField<String>(
          initialValue: _eventStatusFilter,
          decoration: const InputDecoration(
            labelText: 'Event Status',
            border: OutlineInputBorder(),
          ),
          items: const [
            DropdownMenuItem(value: 'All', child: Text('All')),
            DropdownMenuItem(value: 'success', child: Text('success')),
            DropdownMenuItem(value: 'ok', child: Text('ok')),
            DropdownMenuItem(value: 'warning', child: Text('warning')),
            DropdownMenuItem(value: 'failed', child: Text('failed')),
            DropdownMenuItem(value: 'error', child: Text('error')),
            DropdownMenuItem(value: 'unsupported', child: Text('unsupported')),
          ],
          onChanged: (value) {
            if (value == null) return;

            setState(() {
              _eventStatusFilter = value;
            });
          },
        ),
      ),
    ];
  }

  List<Widget> _buildErrorFilterControls() {
    return [
      SizedBox(
        width: 300,
        child: DropdownButtonFormField<String>(
          initialValue: _errorTypeFilter,
          decoration: const InputDecoration(
            labelText: 'Error Type',
            border: OutlineInputBorder(),
          ),
          items: [
            const DropdownMenuItem(value: 'All', child: Text('All')),
            if (!_isPcsAsset) ...const [
              DropdownMenuItem(value: 'SETTINGS_READ_FAILED', child: Text('SETTINGS_READ_FAILED')),
              DropdownMenuItem(value: 'MODBUS_OR_POLLING_ERROR', child: Text('MODBUS_OR_POLLING_ERROR')),
              DropdownMenuItem(value: 'COMMAND_EXECUTION_FAILED', child: Text('COMMAND_EXECUTION_FAILED')),
              DropdownMenuItem(value: 'POST_COMMAND_REFRESH_FAILED', child: Text('POST_COMMAND_REFRESH_FAILED')),
              DropdownMenuItem(value: 'OLD_VALUE_READ_FAILED', child: Text('OLD_VALUE_READ_FAILED')),
            ],
            if (_isPcsAsset) ...const [
              DropdownMenuItem(value: 'PCS_POLLING_ERROR', child: Text('PCS_POLLING_ERROR')),
              DropdownMenuItem(value: 'PCS_COMMAND_FAILED', child: Text('PCS_COMMAND_FAILED')),
              DropdownMenuItem(value: 'PCS_TELEMETRY_LOG_EXCEPTION', child: Text('PCS_TELEMETRY_LOG_EXCEPTION')),
            ],
          ],
          onChanged: (value) {
            if (value == null) return;

            setState(() {
              _errorTypeFilter = value;
            });
          },
        ),
      ),
    ];
  }

  Future<void> _showTelemetryFieldDialog() async {
    final tempSelection = Set<String>.from(_selectedTelemetryFields);

    final result = await showDialog<Set<String>>(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: Text('Select Telemetry Fields - $_selectedAssetId'),
          content: SizedBox(
            width: 620,
            child: StatefulBuilder(
              builder: (context, setDialogState) {
                return SingleChildScrollView(
                  child: Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: _activeTelemetryFieldOrder.map((field) {
                      final selected = tempSelection.contains(field);

                      return FilterChip(
                        label: Text(field),
                        selected: selected,
                        onSelected: (value) {
                          setDialogState(() {
                            if (value) {
                              tempSelection.add(field);
                            } else {
                              tempSelection.remove(field);
                            }
                          });
                        },
                      );
                    }).toList(),
                  ),
                );
              },
            ),
          ),
          actions: [
            TextButton(
              onPressed: () {
                tempSelection.clear();
                tempSelection.addAll(_activeTelemetryFieldOrder);
                Navigator.of(context).pop(tempSelection);
              },
              child: const Text('Select All'),
            ),
            TextButton(
              onPressed: () {
                tempSelection.clear();
                tempSelection.addAll(_defaultTelemetryFieldsForAsset(_selectedAssetId));
                Navigator.of(context).pop(tempSelection);
              },
              child: const Text('Default'),
            ),
            TextButton(
              onPressed: () {
                Navigator.of(context).pop(null);
              },
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () {
                Navigator.of(context).pop(tempSelection);
              },
              child: const Text('Apply'),
            ),
          ],
        );
      },
    );

    if (result == null) return;

    setState(() {
      _selectedTelemetryFields = result;
      _useSelectedTelemetryFields = true;
    });
  }

  Widget _buildTelemetryTab() {
    return _buildLogTable(
      title: 'Telemetry Logs - $_selectedAssetId',
      response: _telemetryLogs,
      preferredColumns: _activeTelemetryPreferredColumns,
    );
  }

  Widget _buildEventsTab() {
    return _buildLogTable(
      title: 'Event Logs - $_selectedAssetId',
      response: _eventLogs,
      preferredColumns: _activeEventPreferredColumns,
    );
  }

  Widget _buildErrorsTab() {
    return _buildLogTable(
      title: 'Error Logs - $_selectedAssetId',
      response: _errorLogs,
      preferredColumns: _activeErrorPreferredColumns,
    );
  }

  Widget _buildLogTable({
    required String title,
    required LogApiResponse? response,
    required List<String> preferredColumns,
  }) {
    return LogDataTable(
      title: title,
      response: response,
      preferredColumns: preferredColumns,
      fallbackAssetId: _selectedAssetId,
    );
  }
  Widget _buildTableHeader(String title, LogApiResponse response) {
    return const SizedBox.shrink();
  }


  Widget _buildStorageTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          StorageStatusCard(status: _storageStatus),
          const SizedBox(height: 12),
          LogFilesCard(
            files: _logFiles,
            assetId: _selectedAssetId,
            onDateSelected: (date) {
              setState(() {
                _dateController.text = date;
              });
              _fetchTelemetryOnly();
            },
          ),
          const SizedBox(height: 12),
          MetadataCard(metadata: _metadata),
        ],
      ),
    );
  }

}
