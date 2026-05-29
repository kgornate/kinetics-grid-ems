import 'dart:async';

import 'package:flutter/material.dart';

import '../config/app_config.dart';
import '../models/log_models.dart';
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

  String _modbusStatusFilter = 'All';
  String _loggerStatusFilter = 'All';
  String _eventTypeFilter = 'All';
  String _eventStatusFilter = 'All';
  String _errorTypeFilter = 'All';

  StorageStatus? _storageStatus;
  LogFilesResponse? _logFiles;
  LogApiResponse? _telemetryLogs;
  LogApiResponse? _eventLogs;
  LogApiResponse? _errorLogs;
  MetadataResponse? _metadata;

  final List<String> _telemetryFieldOrder = const [
    'timestamp',
    'sequence_no',
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

  late Set<String> _selectedTelemetryFields;

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

    _selectedTelemetryFields = {
      'timestamp',
      'outlet_water_temp',
      'return_water_temp',
      'set_temperature',
      'control_mode',
      'system_on_off',
      'modbus_status',
      'logger_status',
    };
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

  String _todayDate() {
    final now = DateTime.now();

    return '${now.year.toString().padLeft(4, '0')}-'
        '${now.month.toString().padLeft(2, '0')}-'
        '${now.day.toString().padLeft(2, '0')}';
  }

  LogApiService _api() {
    return LogApiService(
      gatewayIp: _gatewayIpController.text.trim(),
      port: AppConfig.logHttpPort,
      timeout: AppConfig.httpTimeout,
    );
  }

  String? _filterText(String text) {
    final trimmed = text.trim();
    return trimmed.isEmpty ? null : trimmed;
  }

  String? _filterDropdown(String value) {
    return value.toLowerCase() == 'all' ? null : value;
  }

  String? _telemetryFieldsCsv() {
    if (!_useSelectedTelemetryFields) return null;
    if (_selectedTelemetryFields.isEmpty) return null;

    final ordered = _telemetryFieldOrder.where(_selectedTelemetryFields.contains);

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

  Future<String> _loadStorageAndResolveDate(LogApiService api) async {
    final storage = await api.fetchStorageStatus();
    final files = await api.fetchLogFiles();

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

  Future<void> _refreshAll() async {
    setState(() {
      _loading = true;
      _statusMessage = 'Fetching logs from i.MX93...';
    });

    try {
      final api = _api();

      final effectiveDate = await _loadStorageAndResolveDate(api);

      final results = await Future.wait([
        api.fetchTelemetryLogs(
          date: effectiveDate,
          limit: _limit,
          startTime: _filterText(_startTimeController.text),
          endTime: _filterText(_endTimeController.text),
          fields: _telemetryFieldsCsv(),
          modbusStatus: _filterDropdown(_modbusStatusFilter),
          loggerStatus: _filterDropdown(_loggerStatusFilter),
          search: _filterText(_searchController.text),
        ),
        api.fetchEventLogs(
          date: effectiveDate,
          limit: _limit,
          startTime: _filterText(_startTimeController.text),
          endTime: _filterText(_endTimeController.text),
          eventType: _filterDropdown(_eventTypeFilter),
          status: _filterDropdown(_eventStatusFilter),
          search: _filterText(_searchController.text),
        ),
        api.fetchErrorLogs(
          date: effectiveDate,
          limit: _limit,
          startTime: _filterText(_startTimeController.text),
          endTime: _filterText(_endTimeController.text),
          errorType: _filterDropdown(_errorTypeFilter),
          search: _filterText(_searchController.text),
        ),
        api.fetchMetadata(),
      ]);

      setState(() {
        _telemetryLogs = results[0] as LogApiResponse;
        _eventLogs = results[1] as LogApiResponse;
        _errorLogs = results[2] as LogApiResponse;
        _metadata = results[3] as MetadataResponse;

        _statusMessage = 'Logs refreshed successfully';
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
      _statusMessage = 'Fetching telemetry logs...';
    });

    try {
      final api = _api();
      final effectiveDate = await _loadStorageAndResolveDate(api);

      final logs = await api.fetchTelemetryLogs(
        date: effectiveDate,
        limit: _limit,
        startTime: _filterText(_startTimeController.text),
        endTime: _filterText(_endTimeController.text),
        fields: _telemetryFieldsCsv(),
        modbusStatus: _filterDropdown(_modbusStatusFilter),
        loggerStatus: _filterDropdown(_loggerStatusFilter),
        search: _filterText(_searchController.text),
      );

      setState(() {
        _telemetryLogs = logs;
        _statusMessage = 'Telemetry logs refreshed';
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
      _eventTypeFilter = 'All';
      _eventStatusFilter = 'All';
      _errorTypeFilter = 'All';

      _useSelectedTelemetryFields = false;
    });
  }

  String _value(dynamic value) {
    if (value == null) return '--';

    final text = value.toString();

    if (text.isEmpty) return '--';

    return text;
  }

  @override
  Widget build(BuildContext context) {
    final downloadUrl = _api().telemetryCsvDownloadUrl(
      date: _dateController.text.trim(),
    );

    return DefaultTabController(
      length: 4,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('EMS Logs & History'),
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
                SwitchListTile(
                  dense: true,
                  title: const Text('Show Filters'),
                  value: _showFilters,
                  onChanged: (value) {
                    setState(() {
                      _showFilters = value;
                    });
                  },
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
          width: 240,
          child: TextField(
            controller: _searchController,
            decoration: const InputDecoration(
              labelText: 'Search',
              hintText: 'temperature, mode, error...',
              border: OutlineInputBorder(),
              prefixIcon: Icon(Icons.search),
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
    return [
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
  }

  List<Widget> _buildEventFilterControls() {
    return [
      SizedBox(
        width: 230,
        child: DropdownButtonFormField<String>(
          initialValue: _eventTypeFilter,
          decoration: const InputDecoration(
            labelText: 'Event Type',
            border: OutlineInputBorder(),
          ),
          items: const [
            DropdownMenuItem(value: 'All', child: Text('All')),
            DropdownMenuItem(value: 'SET_TEMPERATURE_WRITE', child: Text('SET_TEMP')),
            DropdownMenuItem(value: 'CONTROL_MODE_WRITE', child: Text('SET_MODE')),
            DropdownMenuItem(value: 'SYSTEM_ON_OFF_WRITE', child: Text('ON/OFF')),
            DropdownMenuItem(value: 'STORAGE_LOGGER_STARTED', child: Text('LOGGER START')),
            DropdownMenuItem(value: 'STORAGE_LOGGER_STOPPED', child: Text('LOGGER STOP')),
          ],
          onChanged: (value) {
            if (value == null) return;

            setState(() {
              _eventTypeFilter = value;
            });
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
            DropdownMenuItem(value: 'warning', child: Text('warning')),
            DropdownMenuItem(value: 'error', child: Text('error')),
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
        width: 260,
        child: DropdownButtonFormField<String>(
          initialValue: _errorTypeFilter,
          decoration: const InputDecoration(
            labelText: 'Error Type',
            border: OutlineInputBorder(),
          ),
          items: const [
            DropdownMenuItem(value: 'All', child: Text('All')),
            DropdownMenuItem(value: 'SETTINGS_READ_FAILED', child: Text('SETTINGS_READ_FAILED')),
            DropdownMenuItem(value: 'MODBUS_OR_POLLING_ERROR', child: Text('MODBUS_OR_POLLING_ERROR')),
            DropdownMenuItem(value: 'COMMAND_EXECUTION_FAILED', child: Text('COMMAND_EXECUTION_FAILED')),
            DropdownMenuItem(value: 'POST_COMMAND_REFRESH_FAILED', child: Text('POST_COMMAND_REFRESH_FAILED')),
            DropdownMenuItem(value: 'OLD_VALUE_READ_FAILED', child: Text('OLD_VALUE_READ_FAILED')),
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
          title: const Text('Select Telemetry Fields'),
          content: SizedBox(
            width: 420,
            child: StatefulBuilder(
              builder: (context, setDialogState) {
                return SingleChildScrollView(
                  child: Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: _telemetryFieldOrder.map((field) {
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
                tempSelection.addAll(_telemetryFieldOrder);
                Navigator.of(context).pop(tempSelection);
              },
              child: const Text('Select All'),
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
      title: 'Telemetry Logs',
      response: _telemetryLogs,
      preferredColumns: const [
        'timestamp',
        'sequence_no',
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
      ],
    );
  }

  Widget _buildEventsTab() {
    return _buildLogTable(
      title: 'Event Logs',
      response: _eventLogs,
      preferredColumns: const [
        'timestamp',
        'event_type',
        'old_value',
        'new_value',
        'source',
        'status',
        'description',
      ],
    );
  }

  Widget _buildErrorsTab() {
    return _buildLogTable(
      title: 'Error Logs',
      response: _errorLogs,
      preferredColumns: const [
        'timestamp',
        'error_type',
        'error_source',
        'description',
      ],
    );
  }

  Widget _buildLogTable({
    required String title,
    required LogApiResponse? response,
    required List<String> preferredColumns,
  }) {
    if (response == null) {
      return _emptyState(
        title: title,
        message: 'Press Refresh Logs to load data from i.MX93.',
      );
    }

    if (!response.isOk) {
      return _emptyState(
        title: title,
        message: response.message ?? 'API returned status: ${response.status}',
      );
    }

    final rows = response.rows;

    if (rows.isEmpty) {
      return _emptyState(
        title: title,
        message: 'No rows found in ${response.fileName ?? 'log file'}.',
      );
    }

    final availableColumns = preferredColumns.where((column) {
      return rows.any((row) => row.containsKey(column));
    }).toList();

    final columns = availableColumns.isNotEmpty
        ? availableColumns
        : rows.first.keys.map((key) => key.toString()).toList();

    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
      child: Card(
        elevation: 1,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildTableHeader(title, response),
            const Divider(height: 1),
            Expanded(
              child: Scrollbar(
                thumbVisibility: true,
                child: SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: SingleChildScrollView(
                    child: DataTable(
                      headingRowColor: WidgetStateProperty.all(
                        Colors.blueGrey.withValues(alpha: 0.08),
                      ),
                      columns: columns.map((column) {
                        return DataColumn(
                          label: Text(
                            column,
                            style: const TextStyle(
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        );
                      }).toList(),
                      rows: rows.map((row) {
                        return DataRow(
                          cells: columns.map((column) {
                            final text = _value(row[column]);
                            final isLong = text.length > 45;

                            return DataCell(
                              SizedBox(
                                width: isLong ? 380 : null,
                                child: SelectableText(
                                  text,
                                  maxLines: isLong ? 3 : 1,
                                ),
                              ),
                            );
                          }).toList(),
                        );
                      }).toList(),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTableHeader(String title, LogApiResponse response) {
    return Padding(
      padding: const EdgeInsets.all(14),
      child: Wrap(
        spacing: 18,
        runSpacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Text(
            title,
            style: const TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.w700,
            ),
          ),
          Text('File: ${response.fileName ?? '--'}'),
          Text('Total rows: ${response.totalRows}'),
          Text('Filtered: ${response.filteredRows}'),
          Text('Showing: ${response.rowsCount}'),
          Text('Limit: ${response.limit}'),
        ],
      ),
    );
  }

  Widget _buildStorageTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _buildStorageStatusCard(),
          const SizedBox(height: 12),
          _buildLogFilesCard(),
          const SizedBox(height: 12),
          _buildMetadataCard(),
        ],
      ),
    );
  }

  Widget _buildStorageStatusCard() {
    final status = _storageStatus;

    return Card(
      elevation: 1,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: status == null
            ? const Text('Storage status not loaded yet.')
            : Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Storage Status',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 12),
                  _infoRow('API Status', status.status),
                  _infoRow('Base Path', status.basePath),
                  _infoRow('Asset ID', status.assetId),
                  _infoRow('Base Path Exists', status.exists.toString()),
                  _infoRow(
                    'Telemetry Directory Exists',
                    status.telemetryDirExists.toString(),
                  ),
                  _infoRow('Events File Exists', status.eventsFileExists.toString()),
                  _infoRow('Errors File Exists', status.errorsFileExists.toString()),
                  _infoRow(
                    'Metadata File Exists',
                    status.metadataFileExists.toString(),
                  ),
                  _infoRow('Telemetry Files', status.telemetryFilesCount.toString()),
                  _infoRow('Latest Telemetry File', status.latestTelemetryFile ?? '--'),
                  const Divider(height: 22),
                  _infoRow('Disk Total', formatBytes(status.diskTotalBytes)),
                  _infoRow('Disk Used', formatBytes(status.diskUsedBytes)),
                  _infoRow('Disk Free', formatBytes(status.diskFreeBytes)),
                  const Divider(height: 22),
                  _infoRow('EMS Logs Total Size', formatBytes(status.logTotalBytes)),
                  _infoRow('Telemetry Logs Size', formatBytes(status.telemetryLogBytes)),
                  _infoRow('Event Log Size', formatBytes(status.eventLogBytes)),
                  _infoRow('Error Log Size', formatBytes(status.errorLogBytes)),
                  _infoRow('Metadata Size', formatBytes(status.metadataBytes)),
                ],
              ),
      ),
    );
  }

  Widget _buildLogFilesCard() {
    final files = _logFiles;

    return Card(
      elevation: 1,
      child: ExpansionTile(
        initiallyExpanded: true,
        title: const Text('Available Telemetry Log Files'),
        subtitle: Text(
          files == null ? 'Not loaded' : '${files.filesCount} file(s) available',
        ),
        children: [
          if (files == null || files.files.isEmpty)
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text('No log files available.'),
            )
          else
            ...files.files.map(
              (file) => ListTile(
                dense: true,
                leading: const Icon(Icons.description),
                title: Text(file),
                onTap: () {
                  final date = file.replaceAll('.csv', '');

                  setState(() {
                    _dateController.text = date;
                  });

                  _fetchTelemetryOnly();
                },
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildMetadataCard() {
    final metadata = _metadata;

    return Card(
      elevation: 1,
      child: ExpansionTile(
        initiallyExpanded: true,
        title: const Text('Gateway Metadata'),
        subtitle: Text(metadata == null ? 'Not loaded' : metadata.status),
        children: [
          if (metadata == null || metadata.metadata.isEmpty)
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text('No metadata loaded.'),
            )
          else
            Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: metadata.metadata.entries.map((entry) {
                  return _infoRow(entry.key, entry.value.toString());
                }).toList(),
              ),
            ),
        ],
      ),
    );
  }

  Widget _infoRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 7),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 220,
            child: Text(
              label,
              style: const TextStyle(
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          Expanded(
            child: SelectableText(value),
          ),
        ],
      ),
    );
  }

  Widget _emptyState({
    required String title,
    required String message,
  }) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
      child: Card(
        elevation: 1,
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(30),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  message,
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}