import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/api/northbound_api_client.dart';
import '../../auth/models/auth_session.dart';
import '../../auth/screens/environment_select_screen.dart';
import '../../auth/services/session_store.dart';
import '../models/dehumidifier_source_snapshot.dart';
import '../models/pcs_fault_item.dart';
import '../models/source_summary.dart';
import '../utils/dehumidifier_page_builder.dart';
import '../widgets/dashboard_nav_actions.dart';
import '../widgets/home_kpi_tile.dart';
import '../widgets/mini_trend_card.dart';
import 'bms_screen.dart';
import 'fire_screen.dart';
import 'home_dashboard_screen.dart';
import 'liquid_cooling_screen.dart';
import 'pcs_screen.dart';
import 'topology_screen.dart';
import 'utility_meter_screen.dart';
import 'ems_system_screen.dart';
import 'strategy_command_screen.dart';

class DehumidifierScreen extends StatefulWidget {
  final AuthSession session;
  final ValueChanged<DashboardPage>? onNavigate;
  final Future<void> Function()? onLogout;

  const DehumidifierScreen({
    super.key,
    required this.session,
    this.onNavigate,
    this.onLogout,
  });

  @override
  State<DehumidifierScreen> createState() => _DehumidifierScreenState();
}

class _DehumidifierScreenState extends State<DehumidifierScreen> {
  static const _maxTrendPoints = 24;
  static const _pollInterval = Duration(seconds: 8);

  bool _bootLoading = true;
  bool _refreshing = false;
  String? _error;
  List<SourceSummary> _sources = const [];
  List<DehumidifierSourceSnapshot> _snapshots = const [];
  String? _selectedSourceId;

  final Map<String, List<TrendPoint>> _tempTrends = {};
  final Map<String, List<TrendPoint>> _humidityTrends = {};

  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _load(initial: true);
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
      case DashboardPage.chiller:
        target = LiquidCoolingScreen(session: widget.session);
        break;
      case DashboardPage.dehumidifier:
        return;
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
        target = StrategyCommandScreen(session: widget.session);
        break;
    }
    Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => target));
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

  Future<void> _load({bool initial = false, bool silent = false}) async {
    if (initial) {
      setState(() {
        _bootLoading = true;
        _error = null;
      });
    } else if (!silent) {
      setState(() {
        _refreshing = true;
        _error = null;
      });
    }

    try {
      final api = NorthboundApiClient(
        baseUrl: widget.session.connection.baseUrl,
        token: widget.session.accessToken,
      );

      final sourcesJson = await api.getSourcesSummary();
      final sourceItems = (sourcesJson['items'] as List? ?? [])
          .whereType<Map<String, dynamic>>()
          .map(SourceSummary.fromJson)
          .toList();

      final snapshots = <DehumidifierSourceSnapshot>[];
      for (final source in sourceItems) {
        final assetsJson = await api.getAssets(sourceId: source.sourceId);
        final assetItems = (assetsJson['items'] as List? ?? []).whereType<Map<String, dynamic>>().toList();
        Map<String, dynamic>? targetAsset;
        for (final item in assetItems) {
          final base = item['base_asset_id']?.toString().toLowerCase() ?? '';
          final assetId = item['asset_id']?.toString().toLowerCase() ?? '';
          if (base == 'dehumidifier' || assetId.contains('dehumidifier') || assetId.contains('cs')) {
            targetAsset = item;
            break;
          }
        }
        Map<String, dynamic>? telemetry;
        if (targetAsset != null) {
          telemetry = await api.getAssetTelemetry(targetAsset['asset_id'].toString(), compact: true, pageSize: 500);
        }
        final snapshot = DehumidifierPageBuilder.buildForSource(
          source: source,
          dehumidifierTelemetry: telemetry,
          fallbackOnline: source.online,
        );
        snapshots.add(snapshot);
        _appendTrend(_tempTrends, source.sourceId, snapshot.currentTemperatureC);
        _appendTrend(_humidityTrends, source.sourceId, snapshot.currentHumidityPct);
      }

      final selected = _selectedSourceId != null && snapshots.any((e) => e.sourceId == _selectedSourceId)
          ? _selectedSourceId
          : (snapshots.isNotEmpty ? snapshots.first.sourceId : null);

      if (!mounted) return;
      setState(() {
        _sources = sourceItems;
        _snapshots = snapshots;
        _selectedSourceId = selected;
        _bootLoading = false;
        _refreshing = false;
      });
    } catch (e) {
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
      });
    }
  }

  void _appendTrend(Map<String, List<TrendPoint>> target, String sourceId, double? value) {
    if (value == null) return;
    final list = target.putIfAbsent(sourceId, () => <TrendPoint>[]);
    list.add(TrendPoint(timestamp: DateTime.now(), value: value));
    if (list.length > _maxTrendPoints) {
      list.removeRange(0, list.length - _maxTrendPoints);
    }
  }

  @override
  Widget build(BuildContext context) {
    final selected = _snapshots
        .where((e) => e.sourceId == _selectedSourceId)
        .cast<DehumidifierSourceSnapshot?>()
        .firstWhere((e) => e != null, orElse: () => _snapshots.isNotEmpty ? _snapshots.first : null);
    final width = MediaQuery.of(context).size.width;
    final wide = width > 1320;

    return Scaffold(
      appBar: AppBar(
        title: const Text('NorthBound EMS Dashboard'),
        actions: [
          DashboardNavActions(
            currentPage: DashboardPage.dehumidifier,
            connectionLabel: '${widget.session.connection.label} • ${widget.session.displayName}',
            onHome: () => _go(DashboardPage.home),
            onTopology: () => _go(DashboardPage.topology),
            onPcs: () => _go(DashboardPage.pcs),
            onBms: () => _go(DashboardPage.bms),
            onChiller: () => _go(DashboardPage.chiller),
            onDehumidifier: () {},
            onFire: () => _go(DashboardPage.fire),
            onUtilityMeter: () => _go(DashboardPage.utilityMeter),
            onEmsSystem: () => _go(DashboardPage.emsSystem),
            onStrategy: () => _go(DashboardPage.strategy),
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
            if (_bootLoading && selected == null)
              const Padding(
                padding: EdgeInsets.all(40),
                child: Center(child: CircularProgressIndicator()),
              )
            else ...[
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Card(
                    child: Padding(
                      padding: const EdgeInsets.all(18),
                      child: Text(_error!, style: const TextStyle(color: Color(0xFFC53939))),
                    ),
                  ),
                ),
              Text(
                'Dehumidifier / CS',
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 14),
              Wrap(
                spacing: 12,
                runSpacing: 12,
                children: _snapshots
                    .map((snapshot) => ChoiceChip(
                          label: Text(snapshot.displayName),
                          selected: snapshot.sourceId == _selectedSourceId,
                          onSelected: (_) => setState(() => _selectedSourceId = snapshot.sourceId),
                        ))
                    .toList(),
              ),
              const SizedBox(height: 18),
              if (selected == null)
                const Card(child: Padding(padding: EdgeInsets.all(18), child: Text('No dehumidifier data available.')))
              else ...[
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(18),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(selected.displayName, style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700)),
                        const SizedBox(height: 6),
                        Text('${selected.sourceId} • ${selected.host}:${selected.port}', style: Theme.of(context).textTheme.bodySmall?.copyWith(color: const Color(0xFF6C7B8A))),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 18),
                GridView.count(
                  crossAxisCount: wide ? 4 : 2,
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  crossAxisSpacing: 12,
                  mainAxisSpacing: 12,
                  childAspectRatio: 1.5,
                  children: [
                    HomeKpiTile(title: 'Current Temperature', value: _fmt(selected.currentTemperatureC, '°C'), subtitle: 'Measured cabinet temperature', icon: Icons.thermostat_rounded),
                    HomeKpiTile(title: 'Current Humidity', value: _fmt(selected.currentHumidityPct, '%'), subtitle: 'Measured cabinet humidity', icon: Icons.water_drop_rounded),
                    HomeKpiTile(title: 'Controller Temperature', value: _fmt(selected.controllerInternalTemperatureC, '°C'), subtitle: 'Controller internal temperature', icon: Icons.memory_rounded),
                    HomeKpiTile(title: 'Online Point', value: selected.onlinePointLabel, subtitle: 'Connectivity / online state', icon: Icons.cloud_done_rounded),
                    HomeKpiTile(title: 'Humidity Control Mode', value: selected.humidityControlModeLabel, subtitle: 'Configured humidity mode', icon: Icons.tune_rounded),
                    HomeKpiTile(title: 'Dehumidification Switch', value: selected.dehumidificationSwitchLabel, subtitle: 'Dehumidification command', icon: Icons.toggle_on_rounded),
                    HomeKpiTile(title: 'Temperature Setting', value: _fmt(selected.temperatureSettingC, '°C'), subtitle: 'Configured temperature target', icon: Icons.device_thermostat_rounded),
                    HomeKpiTile(title: 'Temperature Hysteresis', value: _fmt(selected.temperatureHysteresisC, '°C'), subtitle: 'Configured temperature deadband', icon: Icons.linear_scale_rounded),
                    HomeKpiTile(title: 'Humidity Setting', value: _fmt(selected.humiditySettingPct, '%'), subtitle: 'Configured humidity target', icon: Icons.percent_rounded),
                    HomeKpiTile(title: 'Humidity Hysteresis', value: _fmt(selected.humidityHysteresisPct, '%'), subtitle: 'Configured humidity deadband', icon: Icons.stacked_line_chart_rounded),
                    HomeKpiTile(title: 'Operating Mode', value: selected.operatingModeLabel, subtitle: 'Dehumidifier operating mode', icon: Icons.settings_suggest_rounded),
                    HomeKpiTile(title: 'Temperature Control', value: selected.temperatureControlStatusLabel, subtitle: 'Temperature control state', icon: Icons.hvac_rounded),
                    HomeKpiTile(title: 'Dehumidification Status', value: selected.dehumidificationStatusLabel, subtitle: 'Live dehumidification state', icon: Icons.air_rounded),
                    HomeKpiTile(title: 'Alarm Status', value: selected.alarmStatusLabel, subtitle: 'Alarm status rollup', icon: Icons.warning_amber_rounded),
                    HomeKpiTile(title: 'Communication Baud Rate', value: _fmt(selected.communicationBaudRate, ''), subtitle: 'Configured communication baud rate', icon: Icons.settings_ethernet_rounded),
                    HomeKpiTile(title: 'Fault Summary', value: selected.faultSummaryLabel, subtitle: 'Dehumidifier fault rollup', icon: Icons.error_outline_rounded),
                    HomeKpiTile(title: 'Alarm Summary', value: selected.alarmSummaryLabel, subtitle: 'Dehumidifier alarm rollup', icon: Icons.notifications_active_outlined),
                  ],
                ),
                const SizedBox(height: 18),
                Row(
                  children: [
                    Expanded(
                      child: MiniTrendCard(
                        title: '${selected.displayName} Temperature Trend',
                        subtitle: 'Short in-memory live trend',
                        points: _tempTrends[selected.sourceId] ?? const [],
                        valueFormatter: (v) => '${v.toStringAsFixed(1)} °C',
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: MiniTrendCard(
                        title: '${selected.displayName} Humidity Trend',
                        subtitle: 'Short in-memory live trend',
                        points: _humidityTrends[selected.sourceId] ?? const [],
                        valueFormatter: (v) => '${v.toStringAsFixed(1)} %',
                        minY: 0,
                        maxY: 100,
                        lineColor: const Color(0xFF2DB27D),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 18),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(child: _summaryBand(context, title: 'Active Dehumidifier Faults', items: selected.faultItems, danger: true)),
                    const SizedBox(width: 12),
                    Expanded(child: _summaryBand(context, title: 'Active Dehumidifier Alarms', items: selected.alarmItems, danger: false)),
                  ],
                ),
                const SizedBox(height: 12),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(child: _detailFieldCard(context, 'Dehumidifier Fault Indicators', selected.faultItems, fault: true)),
                    const SizedBox(width: 12),
                    Expanded(child: _detailFieldCard(context, 'Dehumidifier Alarm / Warning Indicators', selected.alarmItems, fault: false)),
                  ],
                ),
                const SizedBox(height: 12),
                _detailFieldCard(context, 'Dehumidifier Configured Settings / Thresholds', selected.configItems, fault: false, maxItems: 24),
              ],
            ],
          ],
        ),
      ),
    );
  }

  Widget _summaryBand(BuildContext context, {required String title, required List<PcsFaultItem> items, required bool danger}) {
    final activeItems = items.where((e) => e.active).toList();
    final accent = danger ? const Color(0xFFD64545) : const Color(0xFFB7791F);
    final baseColor = danger ? const Color(0xFFFDECEC) : const Color(0xFFFFF7E6);

    return Card(
      color: activeItems.isEmpty ? const Color(0xFFF5FAF7) : baseColor,
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
            const SizedBox(height: 10),
            if (activeItems.isEmpty)
              Text('No active ${danger ? 'faults' : 'alarms'}', style: TextStyle(color: accent, fontWeight: FontWeight.w700))
            else
              Wrap(
                spacing: 10,
                runSpacing: 10,
                children: activeItems.take(8).map((item) => Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: accent.withOpacity(0.2)),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(item.displayName, style: const TextStyle(fontWeight: FontWeight.w700)),
                      const SizedBox(height: 4),
                      Text(item.stateLabel, style: TextStyle(color: accent, fontWeight: FontWeight.w700)),
                    ],
                  ),
                )).toList(),
              ),
          ],
        ),
      ),
    );
  }

  Widget _detailFieldCard(BuildContext context, String title, List<PcsFaultItem> items, {required bool fault, int maxItems = 18}) {
    final shown = items.take(maxItems).toList();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
            const SizedBox(height: 12),
            if (shown.isEmpty)
              Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
                decoration: BoxDecoration(
                  color: const Color(0xFFF8FAFD),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: const Color(0xFFE6EBF2)),
                ),
                child: Text(
                  fault
                      ? 'No dedicated dehumidifier fault indicator fields are currently exposed or mapped from this source telemetry.'
                      : 'No dedicated dehumidifier alarm / warning indicator fields are currently exposed or mapped from this source telemetry.',
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: const Color(0xFF5B6775)),
                ),
              )
            else
              ...shown.map((item) => Container(
                    margin: const EdgeInsets.only(bottom: 8),
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                    decoration: BoxDecoration(
                      color: item.active ? (fault ? const Color(0xFFFDECEC) : const Color(0xFFFFF7E6)) : const Color(0xFFF8FAFD),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: const Color(0xFFE6EBF2)),
                    ),
                    child: Row(
                      children: [
                        Expanded(child: Text(item.displayName, style: const TextStyle(fontWeight: FontWeight.w600))),
                        Text(
                          item.stateLabel,
                          style: TextStyle(
                            fontWeight: FontWeight.w700,
                            color: item.active ? (fault ? const Color(0xFFD64545) : const Color(0xFFB7791F)) : const Color(0xFF5B6775),
                          ),
                        ),
                      ],
                    ),
                  )),
            if (items.length > shown.length)
              Text(
                'Showing first ${shown.length} indicators out of ${items.length}.',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(color: const Color(0xFF6C7B8A)),
              ),
          ],
        ),
      ),
    );
  }

  String _fmt(double? value, String unit) {
    if (value == null) return '--';
    if (unit.isEmpty) return value.toStringAsFixed(1);
    return '${value.toStringAsFixed(1)} $unit';
  }
}
