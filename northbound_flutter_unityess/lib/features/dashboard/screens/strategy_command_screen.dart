import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/api/northbound_api_client.dart';
import '../../../core/download/file_download.dart';
import '../../../core/export/controller_history_exporter.dart';
import '../../auth/models/auth_session.dart';
import '../../auth/screens/environment_select_screen.dart';
import '../../auth/services/session_store.dart';
import '../models/controller_operator_models.dart';
import '../models/ems_system_source_snapshot.dart';
import '../models/pcs_fault_item.dart';
import '../models/source_summary.dart';
import '../utils/ems_system_page_builder.dart';
import '../widgets/dashboard_nav_actions.dart';
import '../widgets/home_kpi_tile.dart';
import '../widgets/mini_trend_card.dart';
import 'bms_screen.dart';
import 'fast_bess_historian_screen.dart';
import 'dehumidifier_screen.dart';
import 'ems_system_screen.dart';
import 'fire_screen.dart';
import 'home_dashboard_screen.dart';
import 'liquid_cooling_screen.dart';
import 'pcs_screen.dart';
import 'topology_screen.dart';
import 'utility_meter_screen.dart';

class StrategyCommandScreen extends StatefulWidget {
  final AuthSession session;
  final ValueChanged<DashboardPage>? onNavigate;
  final Future<void> Function()? onLogout;

  const StrategyCommandScreen({
    super.key,
    required this.session,
    this.onNavigate,
    this.onLogout,
  });

  @override
  State<StrategyCommandScreen> createState() => _StrategyCommandScreenState();
}

class _StrategyCommandScreenState extends State<StrategyCommandScreen> {
  static const _maxTrendPoints = 24;
  static const _pollInterval = Duration(seconds: 5);

  bool _bootLoading = true;
  bool _refreshing = false;
  bool _updatingSettings = false;
  String? _controllerError;
  String? _emsError;

  ControllerOperatorStatus? _controllerStatus;
  ControllerSettingsSnapshot? _controllerSettings;
  List<ControllerHistoryEvent> _history = const [];
  String _historyFilter = 'All';
  bool _historyLoading = false;
  bool _historyFullRangeLoading = false;
  bool _cancelHistoryFullRange = false;
  bool _historyExporting = false;
  String? _historyError;
  String? _historyMessage;
  String _historyRangeMode = 'quick';
  String _historyQuickRange = '1h';
  DateTime? _historyCustomFromLocal;
  DateTime? _historyCustomToLocal;
  int _historyLimit = 500;
  String _historyOrder = 'desc';
  int _historyRowsPerPage = 50;
  int _historyTablePage = 0;
  int _historyTotal = 0;
  int _historyFullRangeLoaded = 0;
  static const int _historyApiPageLimit = 1000;
  static const int _historyFullRangeCap = 50000;

  List<SourceSummary> _sources = const [];
  List<EmsSystemSourceSnapshot> _snapshots = const [];
  String? _selectedSourceId;
  final Map<String, List<TrendPoint>> _socTrends = {};
  final Map<String, List<TrendPoint>> _powerTrends = {};

  Timer? _timer;

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _historyCustomToLocal = now;
    _historyCustomFromLocal = now.subtract(const Duration(hours: 1));
    _load(initial: true);
    _loadControllerHistory();
    _timer = Timer.periodic(_pollInterval, (_) => _load(silent: true));
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _go(DashboardPage page) async {
    if (widget.onNavigate != null) {
      widget.onNavigate!(page);
      return;
    }
    _timer?.cancel();
    if (!mounted) return;
    Widget target;
    switch (page) {
      case DashboardPage.home:
        target = HomeDashboardScreen(session: widget.session);
        break;
      case DashboardPage.topology:
        target = TopologyScreen(session: widget.session);
        break;
      case DashboardPage.pcs:
        target = PcsScreen(session: widget.session);
        break;
      case DashboardPage.bms:
        target = BmsScreen(session: widget.session);
        break;
      case DashboardPage.historian:
        target = FastBessHistorianScreen(session: widget.session);
        break;
      case DashboardPage.chiller:
        target = LiquidCoolingScreen(session: widget.session);
        break;
      case DashboardPage.dehumidifier:
        target = DehumidifierScreen(session: widget.session);
        break;
      case DashboardPage.fire:
        target = FireScreen(session: widget.session);
        break;
      case DashboardPage.utilityMeter:
        target = UtilityMeterScreen(session: widget.session);
        break;
      case DashboardPage.emsSystem:
        target = EmsSystemScreen(session: widget.session);
        break;
      case DashboardPage.strategy:
        return;
    }
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => target),
    );
  }

  Future<void> _logout() async {
    if (widget.onLogout != null) {
      await widget.onLogout!();
      return;
    }
    _timer?.cancel();
    await SessionStore().clear();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const EnvironmentSelectScreen()),
      (route) => false,
    );
  }

  bool _isAuthError(Object error) {
    final message = error.toString();
    return message.contains('401') || message.contains('Unauthorized');
  }

  Future<void> _load({bool initial = false, bool silent = false}) async {
    if (!silent && mounted) {
      setState(() {
        if (initial) _bootLoading = true;
        _refreshing = true;
        _controllerError = null;
        _emsError = null;
      });
    }

    final api = NorthboundApiClient(
      baseUrl: widget.session.connection.baseUrl,
      token: widget.session.accessToken,
    );

    ControllerOperatorStatus? controllerStatus = _controllerStatus;
    ControllerSettingsSnapshot? controllerSettings = _controllerSettings;
    String? controllerError;

    try {
      final results = await Future.wait<Map<String, dynamic>>([
        api.getControllerStatus(),
        api.getControllerSettings(),
      ]);
      controllerStatus = ControllerOperatorStatus.fromJson(results[0]);
      controllerSettings = ControllerSettingsSnapshot.fromJson(results[1]);
    } catch (e) {
      if (_isAuthError(e)) {
        api.dispose();
        await _logout();
        return;
      }
      controllerError = e.toString();
    }

    List<SourceSummary> sources = _sources;
    List<EmsSystemSourceSnapshot> snapshots = _snapshots;
    String? selectedSourceId = _selectedSourceId;
    String? emsError;

    try {
      final sourcesJson = await api.getSourcesSummary();
      final assetsJson = await api.getAssets();

      sources = (sourcesJson['items'] as List? ?? const [])
          .whereType<Map>()
          .map((item) => SourceSummary.fromJson(item.cast<String, dynamic>()))
          .toList();

      final assetItems = (assetsJson['items'] as List? ?? const [])
          .whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .toList();

      final built = <EmsSystemSourceSnapshot>[];
      for (final source in sources) {
        Map<String, dynamic>? emsTelemetry;
        for (final asset in assetItems) {
          final sourceId = asset['source_id']?.toString();
          if (sourceId != source.sourceId) continue;
          final baseAsset =
              asset['base_asset_id']?.toString().toLowerCase() ?? '';
          final assetId = asset['asset_id']?.toString().toLowerCase() ?? '';
          if (baseAsset == 'ems_system' ||
              assetId.contains('ems_system') ||
              assetId.contains('existing_ems')) {
            final assetIdValue = asset['asset_id']?.toString();
            if (assetIdValue == null || assetIdValue.isEmpty) continue;
            emsTelemetry = await api.getAssetTelemetry(
              assetIdValue,
              compact: false,
              keyOnly: false,
              pageSize: 4000,
            );
            break;
          }
        }

        final snapshot = EmsSystemPageBuilder.buildForSource(
          source: source,
          emsTelemetry: emsTelemetry,
          fallbackOnline: source.online,
        );
        built.add(snapshot);
        _appendTrend(_socTrends, source.sourceId, snapshot.batterySocPct);
        _appendTrend(
          _powerTrends,
          source.sourceId,
          snapshot.actualActivePowerKw,
        );
      }
      snapshots = built;
      selectedSourceId = selectedSourceId != null &&
              snapshots.any((e) => e.sourceId == selectedSourceId)
          ? selectedSourceId
          : (snapshots.isNotEmpty ? snapshots.first.sourceId : null);
    } catch (e) {
      if (_isAuthError(e)) {
        api.dispose();
        await _logout();
        return;
      }
      emsError = e.toString();
    } finally {
      api.dispose();
    }

    if (!mounted) return;
    setState(() {
      _controllerStatus = controllerStatus;
      _controllerSettings = controllerSettings;
      _controllerError = controllerError;
      _sources = sources;
      _snapshots = snapshots;
      _selectedSourceId = selectedSourceId;
      _emsError = emsError;
      _bootLoading = false;
      _refreshing = false;
    });
  }

  void _appendTrend(
    Map<String, List<TrendPoint>> target,
    String sourceId,
    double? value,
  ) {
    if (value == null) return;
    final list = target.putIfAbsent(sourceId, () => <TrendPoint>[]);
    list.add(TrendPoint(timestamp: DateTime.now(), value: value));
    if (list.length > _maxTrendPoints) {
      list.removeRange(0, list.length - _maxTrendPoints);
    }
  }

  EmsSystemSourceSnapshot? get _selectedSnapshot {
    if (_snapshots.isEmpty) return null;
    for (final snapshot in _snapshots) {
      if (snapshot.sourceId == _selectedSourceId) return snapshot;
    }
    return _snapshots.first;
  }

  Future<void> _editSettings() async {
    final settings = _controllerSettings;
    if (settings == null || !widget.session.isInternal || _updatingSettings) {
      return;
    }

    final high = TextEditingController(text: _compact(settings.highLimit));
    final recovery =
        TextEditingController(text: _compact(settings.recoveryLimit));
    final low = TextEditingController(text: _compact(settings.lowCutoffLimit));
    final lowRecovery =
        TextEditingController(text: _compact(settings.lowRecoveryLimit));

    final patch = await showDialog<Map<String, double>>(
      context: context,
      builder: (dialogContext) {
        String? validationError;
        return StatefulBuilder(
          builder: (context, setDialogState) {
            Widget field(String label, TextEditingController controller) {
              return TextField(
                controller: controller,
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                decoration: InputDecoration(
                  labelText: label,
                  suffixText: '%',
                  border: const OutlineInputBorder(),
                ),
              );
            }

            return AlertDialog(
              title: const Text('Edit SOC control thresholds'),
              content: SizedBox(
                width: 520,
                child: SingleChildScrollView(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Changes are restricted to internal administrators and become effective on the next controller cycle.',
                      ),
                      const SizedBox(height: 18),
                      field('Upper / High SOC limit', high),
                      const SizedBox(height: 12),
                      field('Upper recovery limit', recovery),
                      const SizedBox(height: 12),
                      field('Lower SOC cutoff', low),
                      const SizedBox(height: 12),
                      field('Lower recovery limit', lowRecovery),
                      const SizedBox(height: 12),
                      Text(
                        'Lower-SOC protection is currently ${settings.lowCutoffEnabled ? 'enabled' : 'disabled'}. This screen changes threshold values only.',
                        style: const TextStyle(color: Color(0xFF6C7B8A)),
                      ),
                      if (validationError != null) ...[
                        const SizedBox(height: 12),
                        Text(
                          validationError!,
                          style: const TextStyle(
                            color: Color(0xFFC53939),
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.of(dialogContext).pop(),
                  child: const Text('Cancel'),
                ),
                FilledButton(
                  onPressed: () {
                    final highValue = double.tryParse(high.text.trim());
                    final recoveryValue =
                        double.tryParse(recovery.text.trim());
                    final lowValue = double.tryParse(low.text.trim());
                    final lowRecoveryValue =
                        double.tryParse(lowRecovery.text.trim());

                    if ([
                      highValue,
                      recoveryValue,
                      lowValue,
                      lowRecoveryValue,
                    ].any((v) => v == null || v! < 0 || v > 100)) {
                      setDialogState(() {
                        validationError =
                            'All threshold values must be numbers between 0 and 100.';
                      });
                      return;
                    }

                    if (lowValue! > lowRecoveryValue! ||
                        lowRecoveryValue > recoveryValue! ||
                        recoveryValue >= highValue!) {
                      setDialogState(() {
                        validationError =
                            'Required order: lower cutoff <= lower recovery <= recovery < high limit.';
                      });
                      return;
                    }

                    Navigator.of(dialogContext).pop({
                      'high_limit': highValue,
                      'recovery_limit': recoveryValue,
                      'low_cutoff_limit': lowValue,
                      'low_recovery_limit': lowRecoveryValue,
                    });
                  },
                  child: const Text('Save thresholds'),
                ),
              ],
            );
          },
        );
      },
    );

    high.dispose();
    recovery.dispose();
    low.dispose();
    lowRecovery.dispose();

    if (patch == null || !mounted) return;

    setState(() => _updatingSettings = true);
    final api = NorthboundApiClient(
      baseUrl: widget.session.connection.baseUrl,
      token: widget.session.accessToken,
    );

    try {
      final response = await api.updateControllerSettings(
        highLimit: patch['high_limit'],
        recoveryLimit: patch['recovery_limit'],
        lowCutoffLimit: patch['low_cutoff_limit'],
        lowRecoveryLimit: patch['low_recovery_limit'],
      );
      if (!mounted) return;
      final changed = response['changed'] == true;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            changed
                ? 'Controller thresholds updated. They will apply on the next control cycle.'
                : 'No threshold values changed.',
          ),
        ),
      );
      await _load(silent: true);
    } catch (e) {
      if (_isAuthError(e)) {
        await _logout();
        return;
      }
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Unable to update thresholds: $e')),
      );
    } finally {
      api.dispose();
      if (mounted) setState(() => _updatingSettings = false);
    }
  }


  Future<void> _loadControllerHistory({bool fullRange = false}) async {
    final window = _selectedHistoryWindow();
    if (window.$2.isBefore(window.$1) || window.$2.isAtSameMomentAs(window.$1)) {
      setState(() => _historyError = 'Invalid history window. To date/time must be after From date/time.');
      return;
    }

    if (fullRange) {
      setState(() {
        _historyFullRangeLoading = true;
        _cancelHistoryFullRange = false;
        _historyLoading = false;
        _historyExporting = false;
        _historyError = null;
        _historyMessage = 'Starting full-range controller history load...';
        _historyFullRangeLoaded = 0;
        _historyTablePage = 0;
        _history = const [];
      });
    } else {
      setState(() {
        _historyLoading = true;
        _historyError = null;
        _historyMessage = null;
        _historyTablePage = 0;
      });
    }

    final api = NorthboundApiClient(
      baseUrl: widget.session.connection.baseUrl,
      token: widget.session.accessToken,
    );

    try {
      if (!fullRange) {
        final response = await api.getControllerHistory(
          limit: _historyLimit,
          offset: 0,
          order: _historyOrder,
          eventType: _historyEventTypeFilter,
          severity: _historySeverityFilter,
          device: _historyDeviceFilter,
          result: _historyResultFilter,
          fromTime: _historyApiTime(window.$1),
          toTime: _historyApiTime(window.$2),
        );
        final items = _controllerHistoryItems(response);
        if (!mounted) return;
        setState(() {
          _history = items;
          _historyTotal = _historyFilter == 'BESS'
              ? _visibleHistoryItems(items).length
              : ((response['total'] as num?)?.toInt() ?? items.length);
          _historyLoading = false;
          _historyFullRangeLoaded = items.length;
          _historyMessage = 'Loaded ${items.length} event(s) for ${_selectedHistoryWindowLabel()}.';
        });
        return;
      }

      final collected = <ControllerHistoryEvent>[];
      var offset = 0;
      var total = 0;
      var page = 0;
      while (mounted && !_cancelHistoryFullRange) {
        final response = await api.getControllerHistory(
          limit: _historyApiPageLimit,
          offset: offset,
          order: _historyOrder,
          eventType: _historyEventTypeFilter,
          severity: _historySeverityFilter,
          device: _historyDeviceFilter,
          result: _historyResultFilter,
          fromTime: _historyApiTime(window.$1),
          toTime: _historyApiTime(window.$2),
        );
        final pageItems = _controllerHistoryItems(response);
        total = ((response['total'] as num?)?.toInt() ?? pageItems.length);
        if (pageItems.isEmpty) break;

        collected.addAll(pageItems);
        offset += pageItems.length;
        page += 1;

        if (!mounted) return;
        setState(() {
          _history = List<ControllerHistoryEvent>.unmodifiable(collected);
          _historyTotal = total;
          _historyFullRangeLoaded = collected.length;
          _historyMessage = 'Loaded ${collected.length} / $total controller event(s) across $page API page(s).';
        });

        if (pageItems.length < _historyApiPageLimit || offset >= total) break;
        if (collected.length >= _historyFullRangeCap) {
          if (!mounted) return;
          setState(() {
            _historyMessage = 'Stopped at the app safety cap of $_historyFullRangeCap events. Export will contain the loaded events.';
          });
          break;
        }
        await Future<void>.delayed(const Duration(milliseconds: 100));
      }

      if (!mounted) return;
      final cancelled = _cancelHistoryFullRange;
      setState(() {
        _historyFullRangeLoading = false;
        _cancelHistoryFullRange = false;
        _historyFullRangeLoaded = collected.length;
        _history = List<ControllerHistoryEvent>.unmodifiable(collected);
        _historyTotal = _historyFilter == 'BESS'
            ? _visibleHistoryItems(collected).length
            : total;
        _historyMessage = cancelled
            ? 'Full-range load cancelled. ${collected.length} event(s) remain available for table/export.'
            : 'Full-range load complete. ${collected.length} event(s) loaded for ${_selectedHistoryWindowLabel()}.';
      });
    } catch (e) {
      if (_isAuthError(e)) {
        await _logout();
        return;
      }
      if (!mounted) return;
      setState(() {
        _historyLoading = false;
        _historyFullRangeLoading = false;
        _cancelHistoryFullRange = false;
        _historyError = e.toString();
      });
    } finally {
      api.dispose();
    }
  }

  void _cancelControllerHistoryLoad() {
    if (!_historyFullRangeLoading) return;
    setState(() {
      _cancelHistoryFullRange = true;
      _historyMessage = 'Cancel requested. Waiting for the current API page to finish...';
    });
  }

  List<ControllerHistoryEvent> _controllerHistoryItems(Map<String, dynamic> response) {
    return (response['items'] as List? ?? const [])
        .whereType<Map>()
        .map((item) => ControllerHistoryEvent.fromJson(item.cast<String, dynamic>()))
        .toList();
  }

  String? get _historyEventTypeFilter {
    if (_historyFilter == 'Settings') return 'controller_settings_changed';
    if (_historyFilter == 'BESS') return 'bess_command';
    return null;
  }

  String? get _historySeverityFilter =>
      _historyFilter == 'Errors' ? 'error' : null;

  String? get _historyDeviceFilter =>
      _historyFilter == 'Solis' ? 'Solis' : null;

  String? get _historyResultFilter => null;

  List<ControllerHistoryEvent> _visibleHistoryItems([List<ControllerHistoryEvent>? source]) {
    final items = source ?? _history;
    return items.where((event) {
      switch (_historyFilter) {
        case 'Solis':
          return event.device == 'Solis';
        case 'BESS':
          return event.device == 'X' || event.device == 'Y';
        case 'Settings':
          return event.eventType == 'controller_settings_changed';
        case 'Errors':
          return event.severity.toLowerCase() == 'error' ||
              event.result.toLowerCase() == 'failed';
        default:
          return true;
      }
    }).toList();
  }

  (DateTime, DateTime) _selectedHistoryWindow() {
    if (_historyRangeMode == 'custom' &&
        _historyCustomFromLocal != null &&
        _historyCustomToLocal != null) {
      return (_historyCustomFromLocal!, _historyCustomToLocal!);
    }
    final now = DateTime.now();
    return (now.subtract(_historyQuickDuration(_historyQuickRange)), now);
  }

  Duration _historyQuickDuration(String value) {
    switch (value) {
      case '15m':
        return const Duration(minutes: 15);
      case '6h':
        return const Duration(hours: 6);
      case '24h':
        return const Duration(hours: 24);
      case '7d':
        return const Duration(days: 7);
      case '1h':
      default:
        return const Duration(hours: 1);
    }
  }

  String _historyApiTime(DateTime local) {
    final utc = local.toUtc();
    String two(int value) => value.toString().padLeft(2, '0');
    return '${utc.year.toString().padLeft(4, '0')}-${two(utc.month)}-${two(utc.day)}T${two(utc.hour)}:${two(utc.minute)}:${two(utc.second)}+00:00';
  }

  String _selectedHistoryWindowLabel() {
    final window = _selectedHistoryWindow();
    return '${_formatHistoryDateTime(window.$1)} to ${_formatHistoryDateTime(window.$2)}';
  }

  Future<void> _pickControllerHistoryDateTime({required bool isFrom}) async {
    final current = isFrom
        ? (_historyCustomFromLocal ?? DateTime.now().subtract(const Duration(hours: 1)))
        : (_historyCustomToLocal ?? DateTime.now());
    final date = await showDatePicker(
      context: context,
      initialDate: current,
      firstDate: DateTime(2024),
      lastDate: DateTime.now().add(const Duration(days: 1)),
    );
    if (date == null || !mounted) return;
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(current),
    );
    if (time == null || !mounted) return;
    final selected = DateTime(date.year, date.month, date.day, time.hour, time.minute);
    setState(() {
      if (isFrom) {
        _historyCustomFromLocal = selected;
      } else {
        _historyCustomToLocal = selected;
      }
      _historyTablePage = 0;
    });
  }

  Future<void> _exportControllerHistory(String format) async {
    final events = _visibleHistoryItems();
    if (events.isEmpty) {
      _showHistorySnack('Load SOC controller history first, then export.');
      return;
    }
    setState(() {
      _historyExporting = true;
      _historyError = null;
    });
    try {
      final headers = <String>[
        'Timestamp UTC',
        'Timestamp Local',
        'Event Type',
        'Severity',
        'Device',
        'Controller State',
        'Decision',
        'BESS X SOC %',
        'BESS Y SOC %',
        'Solis State',
        'Solis Power kW',
        'Target',
        'Result',
        'Message',
        'Payload',
      ];
      final rows = events.map((event) => <Object?>[
            event.timestampUtc,
            _formatTime(event.timestampUtc),
            event.eventType,
            event.severity,
            event.device,
            event.controllerState,
            event.decision,
            event.socX,
            event.socY,
            event.solisState,
            event.solisPowerKw,
            event.target,
            event.result,
            event.message,
            event.payload.toString(),
          ]).toList(growable: false);
      final stamp = _historyFileStamp(DateTime.now());
      final range = _historyRangeMode == 'quick' ? _historyQuickRange : 'custom';
      final baseName = 'soc_controller_history_${_historyFilter.toLowerCase()}_${range}_$stamp';
      final result = format == 'xlsx'
          ? await saveBytes(
              bytes: ControllerHistoryExporter.buildXlsxBytes(
                sheetName: 'SOC Controller History',
                headers: headers,
                rows: rows,
              ),
              fileName: '$baseName.xlsx',
              mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
          : await saveBytes(
              bytes: ControllerHistoryExporter.buildCsvBytes(
                headers: headers,
                rows: rows,
              ),
              fileName: '$baseName.csv',
              mimeType: 'text/csv;charset=utf-8',
            );
      if (!mounted) return;
      setState(() {
        _historyExporting = false;
        _historyMessage = result.userMessage;
      });
      _showHistorySnack(result.userMessage);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _historyExporting = false;
        _historyError = 'Controller history export failed: $e';
      });
    }
  }

  void _showHistorySnack(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  String _historyFileStamp(DateTime value) {
    String two(int v) => v.toString().padLeft(2, '0');
    return '${value.year}${two(value.month)}${two(value.day)}_${two(value.hour)}${two(value.minute)}${two(value.second)}';
  }

  String _formatHistoryDateTime(DateTime? value) {
    if (value == null) return '--';
    String two(int v) => v.toString().padLeft(2, '0');
    return '${value.year}-${two(value.month)}-${two(value.day)} ${two(value.hour)}:${two(value.minute)}';
  }

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.of(context).size.width;
    final wide = width > 1180;

    return Scaffold(
      appBar: AppBar(
        title: const Text('NorthBound EMS Dashboard'),
        actions: [
          DashboardNavActions(
            currentPage: DashboardPage.strategy,
            connectionLabel:
                '${widget.session.connection.label} • ${widget.session.displayName}',
            onHome: () => _go(DashboardPage.home),
            onTopology: () => _go(DashboardPage.topology),
            onPcs: () => _go(DashboardPage.pcs),
            onBms: () => _go(DashboardPage.bms),
            onHistorian: () => widget.onNavigate?.call(DashboardPage.historian),
            onChiller: () => _go(DashboardPage.chiller),
            onDehumidifier: () => _go(DashboardPage.dehumidifier),
            onFire: () => _go(DashboardPage.fire),
            onUtilityMeter: () => _go(DashboardPage.utilityMeter),
            onEmsSystem: () => _go(DashboardPage.emsSystem),
            onStrategy: () {},
            onLogout: _logout,
            refreshing: _refreshing,
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => _load(),
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'SOC / Solis Automatic Control',
                        style: Theme.of(context)
                            .textTheme
                            .headlineSmall
                            ?.copyWith(fontWeight: FontWeight.w700),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        'Live operator view of the automatic BESS SOC state machine, Solis control, thresholds and event history.',
                        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                              color: const Color(0xFF6C7B8A),
                            ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 12),
                OutlinedButton.icon(
                  onPressed: _refreshing ? null : () => _load(),
                  icon: const Icon(Icons.refresh_rounded),
                  label: const Text('Refresh'),
                ),
              ],
            ),
            const SizedBox(height: 18),
            if (_bootLoading && _controllerStatus == null)
              const Card(
                child: Padding(
                  padding: EdgeInsets.all(36),
                  child: Center(child: CircularProgressIndicator()),
                ),
              )
            else ...[
              if (_controllerError != null)
                _errorCard(
                  'Controller API unavailable',
                  _controllerError!,
                ),
              if (_controllerStatus != null)
                ..._buildControllerOverview(context, _controllerStatus!, wide),
              const SizedBox(height: 18),
              _buildHistory(context),
              const SizedBox(height: 18),
              _buildExistingEmsReadback(context, wide),
            ],
          ],
        ),
      ),
    );
  }

  List<Widget> _buildControllerOverview(
    BuildContext context,
    ControllerOperatorStatus status,
    bool wide,
  ) {
    if (!status.available) {
      return [
        _errorCard(
          'Controller status not available',
          'The gateway has not published an operator controller snapshot yet.',
        ),
      ];
    }

    final stateColor = status.healthy
        ? const Color(0xFF2E7D5B)
        : const Color(0xFFC53939);

    return [
      Card(
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: stateColor.withOpacity(0.12),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Icon(
                  status.healthy
                      ? Icons.hub_rounded
                      : Icons.warning_amber_rounded,
                  color: stateColor,
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            _friendlyState(status.state),
                            style: Theme.of(context)
                                .textTheme
                                .titleLarge
                                ?.copyWith(fontWeight: FontWeight.w700),
                          ),
                        ),
                        _pill(
                          status.mode,
                          status.mode == 'LIVE'
                              ? const Color(0xFF2E7D5B)
                              : const Color(0xFFB7791F),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Text(
                      _friendlyDecision(status.decision),
                      style: Theme.of(context).textTheme.bodyLarge,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Last controller update: ${_formatTime(status.timestampUtc)}',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: const Color(0xFF6C7B8A),
                          ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
      const SizedBox(height: 14),
      GridView.count(
        crossAxisCount: wide ? 4 : 2,
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        crossAxisSpacing: 12,
        mainAxisSpacing: 12,
        childAspectRatio: wide ? 1.55 : 1.35,
        children: [
          _assetCard(
            context,
            title: 'BESS X',
            primary: _soc(status.bessX.socPercent),
            state: status.bessX.targetState,
            online: status.bessX.online,
            subtitle: 'SOC • target ${status.bessX.targetState}',
            icon: Icons.battery_charging_full_rounded,
          ),
          _assetCard(
            context,
            title: 'BESS Y',
            primary: _soc(status.bessY.socPercent),
            state: status.bessY.targetState,
            online: status.bessY.online,
            subtitle: 'SOC • target ${status.bessY.targetState}',
            icon: Icons.battery_charging_full_rounded,
          ),
          _assetCard(
            context,
            title: 'Solis Inverter',
            primary: status.solis.state,
            state: status.solis.targetState,
            online: status.solis.online,
            subtitle:
                '${_power(status.solis.activePowerKw)} • target ${status.solis.targetState}',
            icon: Icons.solar_power_rounded,
          ),
          _assetCard(
            context,
            title: 'Controller',
            primary: status.healthy ? 'HEALTHY' : 'ATTENTION',
            state: status.state,
            online: status.healthy,
            subtitle: _friendlyState(status.state),
            icon: Icons.settings_input_component_rounded,
          ),
        ],
      ),
      const SizedBox(height: 14),
      _buildThresholdCard(context, status),
      if (!status.healthy || (status.error?.isNotEmpty ?? false)) ...[
        const SizedBox(height: 14),
        _errorCard(
          'Controller communication / cycle warning',
          status.error ?? 'The last controller cycle reported an error.',
        ),
      ],
      const SizedBox(height: 14),
      _buildLogicCard(context, status),
    ];
  }

  Widget _assetCard(
    BuildContext context, {
    required String title,
    required String primary,
    required String state,
    required bool online,
    required String subtitle,
    required IconData icon,
  }) {
    final accent = online ? const Color(0xFF2E7D5B) : const Color(0xFFC53939);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: accent),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    title,
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                ),
                Container(
                  width: 9,
                  height: 9,
                  decoration: BoxDecoration(
                    color: accent,
                    shape: BoxShape.circle,
                  ),
                ),
              ],
            ),
            const Spacer(),
            Text(
              primary,
              style: Theme.of(context)
                  .textTheme
                  .headlineSmall
                  ?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 5),
            Text(
              subtitle,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: const Color(0xFF6C7B8A),
                  ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildThresholdCard(
    BuildContext context,
    ControllerOperatorStatus status,
  ) {
    final settings = _controllerSettings;
    final t = status.thresholds;
    final revision = settings?.revision ?? t.settingsRevision;
    final updatedBy = settings != null && settings.updatedBy.isNotEmpty
        ? settings.updatedBy
        : (t.updatedBy.isNotEmpty ? t.updatedBy : '--');
    final updatedAt = settings != null && settings.updatedAtUtc.isNotEmpty
        ? settings.updatedAtUtc
        : t.updatedAtUtc;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
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
                        'SOC Control Thresholds',
                        style: Theme.of(context)
                            .textTheme
                            .titleMedium
                            ?.copyWith(fontWeight: FontWeight.w700),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        widget.session.isInternal
                            ? 'Internal admin access: threshold editing enabled.'
                            : 'Read-only view. Threshold changes are restricted to internal administration.',
                        style: const TextStyle(color: Color(0xFF6C7B8A)),
                      ),
                    ],
                  ),
                ),
                if (widget.session.isInternal)
                  FilledButton.icon(
                    onPressed:
                        _updatingSettings || settings == null ? null : _editSettings,
                    icon: _updatingSettings
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.edit_rounded),
                    label: const Text('Edit thresholds'),
                  ),
              ],
            ),
            const SizedBox(height: 16),
            Wrap(
              spacing: 12,
              runSpacing: 12,
              children: [
                _thresholdTile(
                  'High SOC',
                  t.highSocPercent ?? settings?.highLimit,
                  'High-SOC trigger',
                ),
                _thresholdTile(
                  'Recovery',
                  t.recoverySocPercent ?? settings?.recoveryLimit,
                  'Solar recovery threshold',
                ),
                _thresholdTile(
                  'Low SOC',
                  t.lowCutoffPercent ?? settings?.lowCutoffLimit,
                  t.lowCutoffEnabled ? 'Protection enabled' : 'Protection disabled',
                ),
                _thresholdTile(
                  'Low Recovery',
                  t.lowRecoveryPercent ?? settings?.lowRecoveryLimit,
                  'Low-SOC recovery threshold',
                ),
              ],
            ),
            const SizedBox(height: 12),
            Text(
              'Revision ${revision ?? '--'} • last changed by $updatedBy • ${_formatTime(updatedAt)}',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: const Color(0xFF6C7B8A),
                  ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _thresholdTile(String title, double? value, String subtitle) {
    return Container(
      width: 210,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFF8FAFD),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE6EBF2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
          const SizedBox(height: 6),
          Text(
            value == null ? '--' : '${_compact(value)}%',
            style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 4),
          Text(
            subtitle,
            style: const TextStyle(fontSize: 12, color: Color(0xFF6C7B8A)),
          ),
        ],
      ),
    );
  }

  Widget _buildLogicCard(
    BuildContext context,
    ControllerOperatorStatus status,
  ) {
    final high = status.thresholds.highSocPercent;
    final recovery = status.thresholds.recoverySocPercent;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Automatic Control State Machine',
              style: Theme.of(context)
                  .textTheme
                  .titleMedium
                  ?.copyWith(fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 12),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: DataTable(
                columns: const [
                  DataColumn(label: Text('SOC condition')),
                  DataColumn(label: Text('BESS X')),
                  DataColumn(label: Text('BESS Y')),
                  DataColumn(label: Text('Solis')),
                  DataColumn(label: Text('Action')),
                ],
                rows: [
                  DataRow(cells: [
                    DataCell(Text('Both below ${_pct(high)}')),
                    const DataCell(Text('ON')),
                    const DataCell(Text('ON')),
                    const DataCell(Text('ON')),
                    const DataCell(Text('Normal operation')),
                  ]),
                  DataRow(cells: [
                    DataCell(Text('X >= ${_pct(high)}, Y below')),
                    const DataCell(Text('OFF')),
                    const DataCell(Text('ON')),
                    const DataCell(Text('ON')),
                    const DataCell(Text('X held from further charging')),
                  ]),
                  DataRow(cells: [
                    DataCell(Text('Y >= ${_pct(high)}, X below')),
                    const DataCell(Text('ON')),
                    const DataCell(Text('OFF')),
                    const DataCell(Text('ON')),
                    const DataCell(Text('Y held from further charging')),
                  ]),
                  DataRow(cells: [
                    DataCell(Text('Both >= ${_pct(high)}')),
                    const DataCell(Text('ON')),
                    const DataCell(Text('ON')),
                    const DataCell(Text('OFF')),
                    const DataCell(Text('Solar charging stopped')),
                  ]),
                  DataRow(cells: [
                    DataCell(Text('Recovery <= ${_pct(recovery)} + trend')),
                    const DataCell(Text('ON')),
                    const DataCell(Text('ON')),
                    const DataCell(Text('ON')),
                    const DataCell(Text('Return to normal operation')),
                  ]),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHistory(BuildContext context) {
    final filters = ['All', 'Solis', 'BESS', 'Settings', 'Errors'];
    final visible = _visibleHistoryItems();
    final totalPages = visible.isEmpty
        ? 1
        : ((visible.length + _historyRowsPerPage - 1) ~/ _historyRowsPerPage);
    if (_historyTablePage >= totalPages) _historyTablePage = totalPages - 1;
    final startIndex = (_historyTablePage * _historyRowsPerPage).clamp(0, visible.length).toInt();
    final endIndex = (startIndex + _historyRowsPerPage).clamp(0, visible.length).toInt();
    final pageItems = visible.sublist(startIndex, endIndex);
    final busy = _historyLoading || _historyFullRangeLoading || _historyExporting;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'SOC Controller Historian',
                        style: Theme.of(context)
                            .textTheme
                            .titleLarge
                            ?.copyWith(fontWeight: FontWeight.w700),
                      ),
                      const SizedBox(height: 4),
                      const Text(
                        'Query controller decisions, BESS actions, Solis events, settings changes and errors using quick or custom date/time ranges.',
                        style: TextStyle(color: Color(0xFF6C7B8A)),
                      ),
                    ],
                  ),
                ),
                if (_history.isNotEmpty)
                  Text(
                    '${visible.length} loaded / $_historyTotal matching',
                    style: const TextStyle(color: Color(0xFF6C7B8A)),
                  ),
              ],
            ),
            const SizedBox(height: 16),
            Wrap(
              spacing: 12,
              runSpacing: 12,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                _historyDropdown(
                  label: 'Range mode',
                  value: _historyRangeMode,
                  items: const {
                    'quick': 'Quick range',
                    'custom': 'Custom date/time',
                  },
                  onChanged: (value) => setState(() {
                    _historyRangeMode = value;
                    _historyTablePage = 0;
                  }),
                ),
                if (_historyRangeMode == 'quick')
                  _historyDropdown(
                    label: 'Time range',
                    value: _historyQuickRange,
                    items: const {
                      '15m': 'Last 15 min',
                      '1h': 'Last 1 hour',
                      '6h': 'Last 6 hours',
                      '24h': 'Last 24 hours',
                      '7d': 'Last 7 days',
                    },
                    onChanged: (value) => setState(() {
                      _historyQuickRange = value;
                      _historyTablePage = 0;
                    }),
                  ),
                _historyDropdown(
                  label: 'Load limit',
                  value: _historyLimit.toString(),
                  items: const {
                    '100': '100 events',
                    '500': '500 events',
                    '1000': '1000 events',
                  },
                  onChanged: (value) => setState(() {
                    _historyLimit = int.parse(value);
                    _historyTablePage = 0;
                  }),
                ),
                _historyDropdown(
                  label: 'Order',
                  value: _historyOrder,
                  items: const {
                    'desc': 'Latest first',
                    'asc': 'Oldest first',
                  },
                  onChanged: (value) => setState(() {
                    _historyOrder = value;
                    _historyTablePage = 0;
                  }),
                ),
                _historyDropdown(
                  label: 'Rows / page',
                  value: _historyRowsPerPage.toString(),
                  items: const {
                    '25': '25 rows',
                    '50': '50 rows',
                    '100': '100 rows',
                  },
                  onChanged: (value) => setState(() {
                    _historyRowsPerPage = int.parse(value);
                    _historyTablePage = 0;
                  }),
                ),
              ],
            ),
            if (_historyRangeMode == 'custom') ...[
              const SizedBox(height: 12),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                children: [
                  OutlinedButton.icon(
                    onPressed: busy
                        ? null
                        : () => _pickControllerHistoryDateTime(isFrom: true),
                    icon: const Icon(Icons.calendar_month_rounded),
                    label: Text('From: ${_formatHistoryDateTime(_historyCustomFromLocal)}'),
                  ),
                  OutlinedButton.icon(
                    onPressed: busy
                        ? null
                        : () => _pickControllerHistoryDateTime(isFrom: false),
                    icon: const Icon(Icons.event_rounded),
                    label: Text('To: ${_formatHistoryDateTime(_historyCustomToLocal)}'),
                  ),
                  TextButton(
                    onPressed: busy
                        ? null
                        : () {
                            final now = DateTime.now();
                            setState(() {
                              _historyCustomToLocal = now;
                              _historyCustomFromLocal =
                                  now.subtract(const Duration(hours: 1));
                              _historyTablePage = 0;
                            });
                          },
                    child: const Text('Set last 1 hour'),
                  ),
                  TextButton(
                    onPressed: busy
                        ? null
                        : () {
                            final now = DateTime.now();
                            setState(() {
                              _historyCustomToLocal = now;
                              _historyCustomFromLocal =
                                  now.subtract(const Duration(hours: 24));
                              _historyTablePage = 0;
                            });
                          },
                    child: const Text('Set last 24 hours'),
                  ),
                ],
              ),
            ],
            const SizedBox(height: 10),
            Text(
              'Selected window: ${_selectedHistoryWindowLabel()}',
              style: const TextStyle(
                color: Color(0xFF5B6775),
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 14),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: filters
                  .map(
                    (filter) => ChoiceChip(
                      label: Text(filter),
                      selected: _historyFilter == filter,
                      onSelected: busy
                          ? null
                          : (_) => setState(() {
                                _historyFilter = filter;
                                _historyTablePage = 0;
                              }),
                    ),
                  )
                  .toList(),
            ),
            const SizedBox(height: 14),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                FilledButton.icon(
                  onPressed: busy ? null : () => _loadControllerHistory(),
                  icon: const Icon(Icons.manage_search_rounded),
                  label: Text(_historyLoading ? 'Loading...' : 'Load history'),
                ),
                FilledButton.tonalIcon(
                  onPressed: busy
                      ? null
                      : () => _loadControllerHistory(fullRange: true),
                  icon: const Icon(Icons.downloading_rounded),
                  label: Text(_historyFullRangeLoading
                      ? 'Loading full range...'
                      : 'Load full range for export'),
                ),
                if (_historyFullRangeLoading)
                  OutlinedButton.icon(
                    onPressed: _cancelControllerHistoryLoad,
                    icon: const Icon(Icons.stop_circle_outlined),
                    label: const Text('Cancel loading'),
                  ),
                OutlinedButton.icon(
                  onPressed: visible.isEmpty || busy
                      ? null
                      : () => _exportControllerHistory('csv'),
                  icon: const Icon(Icons.download_rounded),
                  label: const Text('Download CSV'),
                ),
                OutlinedButton.icon(
                  onPressed: visible.isEmpty || busy
                      ? null
                      : () => _exportControllerHistory('xlsx'),
                  icon: const Icon(Icons.table_chart_rounded),
                  label: Text(_historyExporting ? 'Exporting...' : 'Download Excel'),
                ),
                OutlinedButton.icon(
                  onPressed: busy
                      ? null
                      : () => setState(() {
                            _history = const [];
                            _historyTotal = 0;
                            _historyFullRangeLoaded = 0;
                            _historyTablePage = 0;
                            _historyMessage = null;
                            _historyError = null;
                          }),
                  icon: const Icon(Icons.clear_rounded),
                  label: const Text('Clear table'),
                ),
              ],
            ),
            if (_historyFullRangeLoading || _historyMessage != null) ...[
              const SizedBox(height: 12),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: const Color(0xFFF8FAFD),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: const Color(0xFFDDE5EF)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (_historyFullRangeLoading)
                      const LinearProgressIndicator(),
                    if (_historyFullRangeLoading) const SizedBox(height: 8),
                    Text(_historyMessage ?? ''),
                    if (_historyFullRangeLoaded > 0) ...[
                      const SizedBox(height: 4),
                      Text(
                        'Loaded events: $_historyFullRangeLoaded. Safety cap: $_historyFullRangeCap.',
                        style: const TextStyle(color: Color(0xFF5B6775)),
                      ),
                    ],
                  ],
                ),
              ),
            ],
            if (_historyError != null) ...[
              const SizedBox(height: 12),
              _errorCard('SOC historian query/export error', _historyError!),
            ],
            const SizedBox(height: 16),
            if (pageItems.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 18),
                child: Text('No controller events loaded for the selected range/filter.'),
              )
            else ...[
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: DataTable(
                  columnSpacing: 26,
                  columns: const [
                    DataColumn(label: Text('Time')),
                    DataColumn(label: Text('Event')),
                    DataColumn(label: Text('Device')),
                    DataColumn(label: Text('State')),
                    DataColumn(label: Text('X SOC')),
                    DataColumn(label: Text('Y SOC')),
                    DataColumn(label: Text('Solis')),
                    DataColumn(label: Text('Power')),
                    DataColumn(label: Text('Target')),
                    DataColumn(label: Text('Result')),
                    DataColumn(label: Text('Message')),
                  ],
                  rows: pageItems.map((event) {
                    return DataRow(cells: [
                      DataCell(Text(_formatTime(event.timestampUtc))),
                      DataCell(Text(_friendlyEventType(event.eventType))),
                      DataCell(Text(event.device.isEmpty ? '--' : event.device)),
                      DataCell(Text(
                        event.controllerState.isEmpty
                            ? '--'
                            : _friendlyState(event.controllerState),
                      )),
                      DataCell(Text(_soc(event.socX))),
                      DataCell(Text(_soc(event.socY))),
                      DataCell(Text(
                        event.solisState.isEmpty ? '--' : event.solisState,
                      )),
                      DataCell(Text(
                        event.solisPowerKw == null
                            ? '--'
                            : '${event.solisPowerKw!.toStringAsFixed(2)} kW',
                      )),
                      DataCell(Text(event.target.isEmpty ? '--' : event.target)),
                      DataCell(_resultBadge(event.result, event.severity)),
                      DataCell(
                        SizedBox(
                          width: 360,
                          child: Text(
                            event.message,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ),
                    ]);
                  }).toList(),
                ),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Text(
                    'Rows ${startIndex + 1}-$endIndex of ${visible.length}',
                    style: const TextStyle(color: Color(0xFF6C7B8A)),
                  ),
                  const Spacer(),
                  IconButton(
                    tooltip: 'Previous page',
                    onPressed: _historyTablePage <= 0
                        ? null
                        : () => setState(() => _historyTablePage -= 1),
                    icon: const Icon(Icons.chevron_left_rounded),
                  ),
                  Text('Page ${_historyTablePage + 1} / $totalPages'),
                  IconButton(
                    tooltip: 'Next page',
                    onPressed: _historyTablePage >= totalPages - 1
                        ? null
                        : () => setState(() => _historyTablePage += 1),
                    icon: const Icon(Icons.chevron_right_rounded),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _historyDropdown({
    required String label,
    required String value,
    required Map<String, String> items,
    required ValueChanged<String> onChanged,
  }) {
    return SizedBox(
      width: 190,
      child: DropdownButtonFormField<String>(
        value: value,
        decoration: InputDecoration(
          labelText: label,
          border: const OutlineInputBorder(),
        ),
        items: items.entries
            .map(
              (entry) => DropdownMenuItem<String>(
                value: entry.key,
                child: Text(entry.value),
              ),
            )
            .toList(),
        onChanged: (next) {
          if (next != null) onChanged(next);
        },
      ),
    );
  }

  Widget _buildExistingEmsReadback(BuildContext context, bool wide) {
    final selected = _selectedSnapshot;
    return Card(
      child: ExpansionTile(
        initiallyExpanded: false,
        title: const Text(
          'Existing EMS Strategy / Command Readback',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
        subtitle: const Text(
          'Original source-level EMS mode, command and configured-limit diagnostics.',
        ),
        childrenPadding: const EdgeInsets.fromLTRB(18, 0, 18, 18),
        children: [
          if (_emsError != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: _errorCard('EMS readback unavailable', _emsError!),
            ),
          if (_snapshots.isEmpty)
            const Padding(
              padding: EdgeInsets.all(14),
              child: Text('No strategy / command data available.'),
            )
          else ...[
            Align(
              alignment: Alignment.centerLeft,
              child: Wrap(
                spacing: 10,
                runSpacing: 10,
                children: _snapshots
                    .map(
                      (snapshot) => ChoiceChip(
                        label: Text(snapshot.displayName),
                        selected: snapshot.sourceId == _selectedSourceId,
                        onSelected: (_) => setState(
                          () => _selectedSourceId = snapshot.sourceId,
                        ),
                      ),
                    )
                    .toList(),
              ),
            ),
            const SizedBox(height: 14),
            if (selected != null) ...[
              GridView.count(
                crossAxisCount: wide ? 4 : 2,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                crossAxisSpacing: 12,
                mainAxisSpacing: 12,
                childAspectRatio: 1.5,
                children: [
                  HomeKpiTile(
                    title: 'System Status',
                    value: selected.systemStatusLabel,
                    subtitle: 'Overall EMS operating state',
                    icon: Icons.dashboard_customize_rounded,
                  ),
                  HomeKpiTile(
                    title: 'Manual / Auto',
                    value: selected.manualAutoModeLabel,
                    subtitle: 'Control authority selection',
                    icon: Icons.swap_horiz_rounded,
                  ),
                  HomeKpiTile(
                    title: 'Manual Mode',
                    value: selected.manualModeControlLabel,
                    subtitle: 'Manual mode readback',
                    icon: Icons.handyman_rounded,
                  ),
                  HomeKpiTile(
                    title: 'Auto Mode',
                    value: selected.autoModeControlLabel,
                    subtitle: 'Automatic strategy readback',
                    icon: Icons.auto_mode_rounded,
                  ),
                  HomeKpiTile(
                    title: 'Charge Cutoff SOC',
                    value: _fmt(selected.chargeCutoffSocPct, '%'),
                    subtitle: 'Configured charge cutoff threshold',
                    icon: Icons.arrow_upward_rounded,
                  ),
                  HomeKpiTile(
                    title: 'Discharge Cutoff SOC',
                    value: _fmt(selected.dischargeCutoffSocPct, '%'),
                    subtitle: 'Configured discharge cutoff threshold',
                    icon: Icons.arrow_downward_rounded,
                  ),
                  HomeKpiTile(
                    title: 'Charge Limit',
                    value: _fmt(selected.chargeLimitKw, 'kW'),
                    subtitle: 'Configured charge limit',
                    icon: Icons.bolt_rounded,
                  ),
                  HomeKpiTile(
                    title: 'Discharge Limit',
                    value: _fmt(selected.dischargeLimitKw, 'kW'),
                    subtitle: 'Configured discharge limit',
                    icon: Icons.electric_bolt_rounded,
                  ),
                ],
              ),
              const SizedBox(height: 14),
              Row(
                children: [
                  Expanded(
                    child: MiniTrendCard(
                      title: '${selected.displayName} Battery SOC',
                      points: _socTrends[selected.sourceId] ?? const [],
                      unit: '%',
                      lineColor: const Color(0xFF4B74D6),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: MiniTrendCard(
                      title: '${selected.displayName} Active Power',
                      points: _powerTrends[selected.sourceId] ?? const [],
                      unit: 'kW',
                      lineColor: const Color(0xFF2DB27D),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              _commandReadbackCard(context, selected),
              const SizedBox(height: 12),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: _summaryBand(
                      context,
                      title: 'Active EMS Faults',
                      items: selected.faultItems,
                      danger: true,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: _summaryBand(
                      context,
                      title: 'Active EMS Alarms',
                      items: selected.alarmItems,
                      danger: false,
                    ),
                  ),
                ],
              ),
            ],
          ],
        ],
      ),
    );
  }

  Widget _commandReadbackCard(
    BuildContext context,
    EmsSystemSourceSnapshot snapshot,
  ) {
    final commandish = snapshot.configItems.where((item) {
      final key = item.signalName.toLowerCase();
      return key.contains('control') ||
          key.contains('command') ||
          key.contains('mode') ||
          key.contains('power_on');
    }).take(24).toList();

    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: const Color(0xFFF8FAFD),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFE6EBF2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Command Register Readback',
            style: Theme.of(context)
                .textTheme
                .titleMedium
                ?.copyWith(fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 12),
          if (commandish.isEmpty)
            const Text('No command/readback fields exposed for this source.')
          else
            ...commandish
                .map((item) => _valueRow(item.displayName, item.stateLabel)),
        ],
      ),
    );
  }

  Widget _valueRow(String label, String value) => Container(
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: const Color(0xFFE6EBF2)),
        ),
        child: Row(
          children: [
            Expanded(
              child: Text(
                label,
                style: const TextStyle(fontWeight: FontWeight.w600),
              ),
            ),
            Text(
              value,
              style: const TextStyle(
                fontWeight: FontWeight.w700,
                color: Color(0xFF5B6775),
              ),
            ),
          ],
        ),
      );

  Widget _summaryBand(
    BuildContext context, {
    required String title,
    required List<PcsFaultItem> items,
    required bool danger,
  }) {
    final activeItems = items.where((e) => e.active).toList();
    final accent = danger ? const Color(0xFFD64545) : const Color(0xFFB7791F);
    final baseColor =
        danger ? const Color(0xFFFDECEC) : const Color(0xFFFFF7E6);
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: activeItems.isEmpty ? const Color(0xFFF5FAF7) : baseColor,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: Theme.of(context)
                .textTheme
                .titleMedium
                ?.copyWith(fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 10),
          if (activeItems.isEmpty)
            Text(
              'No active ${danger ? 'faults' : 'alarms'}',
              style: TextStyle(color: accent, fontWeight: FontWeight.w700),
            )
          else
            ...activeItems.take(8).map(
                  (item) => Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: Text('${item.displayName}: ${item.stateLabel}'),
                  ),
                ),
        ],
      ),
    );
  }

  Widget _errorCard(String title, String message) {
    return Card(
      color: const Color(0xFFFFF4F4),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.warning_amber_rounded, color: Color(0xFFC53939)),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
                  const SizedBox(height: 4),
                  Text(message),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _pill(String text, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withOpacity(0.12),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        text,
        style: TextStyle(color: color, fontWeight: FontWeight.w700),
      ),
    );
  }

  Widget _resultBadge(String result, String severity) {
    final normalized = result.toLowerCase();
    final error = normalized == 'failed' || severity.toLowerCase() == 'error';
    final color = error ? const Color(0xFFC53939) : const Color(0xFF2E7D5B);
    final label = result.isEmpty ? severity.toUpperCase() : result.toUpperCase();
    return _pill(label, color);
  }

  static String _friendlyState(String state) {
    switch (state) {
      case 'NORMAL':
        return 'Normal Operation';
      case 'X_HIGH_ONLY':
        return 'BESS X High SOC';
      case 'Y_HIGH_ONLY':
        return 'BESS Y High SOC';
      case 'BOTH_HIGH_SOLAR_OFF':
        return 'Both BESS High - Solar Off';
      case 'X_LOW_CUTOFF':
        return 'BESS X Low-SOC Protection';
      case 'Y_LOW_CUTOFF':
        return 'BESS Y Low-SOC Protection';
      case 'BOTH_LOW_CUTOFF_LOCKOUT':
        return 'Both BESS Low-SOC Protection';
      default:
        return state.isEmpty ? 'Unknown' : state.replaceAll('_', ' ');
    }
  }

  static String _friendlyDecision(String decision) {
    switch (decision) {
      case 'normal_keep_both_on_solar_on':
        return 'Both BESS are available and the Solis inverter remains ON.';
      case 'only_x_high_x_off_y_on_solar_on':
        return 'BESS X has reached the high-SOC limit. X is held OFF while BESS Y and Solis remain ON.';
      case 'only_y_high_x_on_y_off_solar_on':
        return 'BESS Y has reached the high-SOC limit. Y is held OFF while BESS X and Solis remain ON.';
      case 'both_high_keep_both_on_solar_off':
        return 'Both BESS reached the high-SOC limit. Solis is commanded OFF to stop further solar charging.';
      case 'both_high_solar_off_waiting_for_recovery':
        return 'Solar remains OFF while the controller waits for the configured SOC recovery condition.';
      case 'post_both_high_recovered_solar_on_both_bess_on':
        return 'SOC recovery condition has been satisfied. Solis and both BESS return to normal operation.';
      case 'x_low_cutoff_x_off_y_on':
      case 'x_low_cutoff_hold_x_off_y_on_until_recovery':
        return 'BESS X is held OFF by the low-SOC protection logic.';
      case 'y_low_cutoff_x_on_y_off':
      case 'y_low_cutoff_hold_x_on_y_off_until_recovery':
        return 'BESS Y is held OFF by the low-SOC protection logic.';
      case 'both_low_cutoff_both_off':
      case 'both_low_cutoff_hold_both_off_until_recovery':
        return 'Both BESS are held OFF by the low-SOC protection logic.';
      default:
        return decision.isEmpty
            ? 'Waiting for controller decision.'
            : decision.replaceAll('_', ' ');
    }
  }

  static String _friendlyEventType(String value) {
    if (value.isEmpty) return '--';
    return value
        .split('_')
        .where((part) => part.isNotEmpty)
        .map((part) => '${part[0].toUpperCase()}${part.substring(1)}')
        .join(' ');
  }

  static String _formatTime(String value) {
    if (value.isEmpty) return '--';
    try {
      final local = DateTime.parse(value).toLocal();
      String two(int v) => v.toString().padLeft(2, '0');
      return '${two(local.day)}/${two(local.month)} ${two(local.hour)}:${two(local.minute)}:${two(local.second)}';
    } catch (_) {
      return value;
    }
  }

  static String _soc(double? value) =>
      value == null ? '--' : '${value.toStringAsFixed(1)}%';

  static String _power(double? value) =>
      value == null ? 'Power --' : '${value.toStringAsFixed(2)} kW';

  static String _pct(double? value) =>
      value == null ? '--' : '${_compact(value)}%';

  static String _compact(double value) {
    return value == value.roundToDouble()
        ? value.toInt().toString()
        : value.toStringAsFixed(1);
  }

  static String _fmt(double? value, String unit) {
    if (value == null) return '--';
    final suffix = unit.trim().isNotEmpty ? ' $unit' : '';
    return '${value.toStringAsFixed(1)}$suffix';
  }
}
