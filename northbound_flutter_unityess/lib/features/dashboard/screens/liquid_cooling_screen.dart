import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/api/northbound_api_client.dart';
import '../../auth/models/auth_session.dart';
import '../../auth/screens/environment_select_screen.dart';
import '../../auth/services/session_store.dart';
import '../models/liquid_cooling_source_snapshot.dart';
import '../models/pcs_fault_item.dart';
import '../models/source_summary.dart';
import '../utils/liquid_cooling_page_builder.dart';
import '../widgets/dashboard_nav_actions.dart';
import '../widgets/home_kpi_tile.dart';
import '../widgets/mini_trend_card.dart';
import 'bms_screen.dart';
import 'home_dashboard_screen.dart';
import 'pcs_screen.dart';
import 'topology_screen.dart';

class LiquidCoolingScreen extends StatefulWidget {
  final AuthSession session;
  final ValueChanged<DashboardPage>? onNavigate;
  final Future<void> Function()? onLogout;

  const LiquidCoolingScreen({
    super.key,
    required this.session,
    this.onNavigate,
    this.onLogout,
  });

  @override
  State<LiquidCoolingScreen> createState() => _LiquidCoolingScreenState();
}

class _LiquidCoolingScreenState extends State<LiquidCoolingScreen> {
  static const _maxTrendPoints = 24;
  static const _pollInterval = Duration(seconds: 8);

  bool _bootLoading = true;
  bool _refreshing = false;
  String? _error;
  List<SourceSummary> _sources = const [];
  List<LiquidCoolingSourceSnapshot> _snapshots = const [];
  String? _selectedSourceId;

  final Map<String, List<TrendPoint>> _tempTrends = {};
  final Map<String, List<TrendPoint>> _pressureTrends = {};

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
        return;
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

      final snapshots = <LiquidCoolingSourceSnapshot>[];
      for (final source in sourceItems) {
        final assetsJson = await api.getAssets(sourceId: source.sourceId);
        final assetItems = (assetsJson['items'] as List? ?? []).whereType<Map<String, dynamic>>().toList();
        Map<String, dynamic>? coolingAsset;
        for (final item in assetItems) {
          final baseAsset = item['base_asset_id']?.toString().toLowerCase() ?? '';
          final assetId = item['asset_id']?.toString().toLowerCase() ?? '';
          if (baseAsset == 'liquid_cooling' || assetId.contains('liquid_cooling') || assetId.contains('chiller')) {
            coolingAsset = item;
            break;
          }
        }
        Map<String, dynamic>? coolingTelemetry;
        if (coolingAsset != null) {
          coolingTelemetry = await api.getAssetTelemetry(coolingAsset['asset_id'].toString(), compact: true, pageSize: 500);
        }
        final snapshot = LiquidCoolingPageBuilder.buildForSource(
          source: source,
          coolingTelemetry: coolingTelemetry,
          fallbackOnline: source.online,
        );
        snapshots.add(snapshot);
        _appendTrend(_tempTrends, source.sourceId, snapshot.inletWaterTempC ?? snapshot.outletWaterTempC);
        _appendTrend(_pressureTrends, source.sourceId, snapshot.inletWaterPressureBar ?? snapshot.outletWaterPressureBar);
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
        .cast<LiquidCoolingSourceSnapshot?>()
        .firstWhere((e) => e != null, orElse: () => _snapshots.isNotEmpty ? _snapshots.first : null);
    final width = MediaQuery.of(context).size.width;
    final wide = width > 1320;

    return Scaffold(
      appBar: AppBar(
        title: const Text('NorthBound EMS Dashboard'),
        actions: [
          DashboardNavActions(
            currentPage: DashboardPage.chiller,
            connectionLabel: '${widget.session.connection.label} • ${widget.session.displayName}',
            onHome: () => _go(DashboardPage.home),
            onTopology: () => _go(DashboardPage.topology),
            onPcs: () => _go(DashboardPage.pcs),
            onBms: () => _go(DashboardPage.bms),
            onChiller: () {},
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
                'Liquid Cooling / Chiller',
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 14),
              Wrap(
                spacing: 12,
                runSpacing: 12,
                children: _snapshots.map((snapshot) => ChoiceChip(
                  label: Text(snapshot.displayName),
                  selected: snapshot.sourceId == _selectedSourceId,
                  onSelected: (_) => setState(() => _selectedSourceId = snapshot.sourceId),
                )).toList(),
              ),
              const SizedBox(height: 18),
              if (selected == null)
                const Card(child: Padding(padding: EdgeInsets.all(18), child: Text('No liquid cooling data available.')))
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
                    HomeKpiTile(title: 'Online', value: selected.online ? 'Online' : 'Offline', subtitle: 'Cooling system connectivity', icon: Icons.cloud_done_rounded),
                    HomeKpiTile(title: 'Power Status', value: selected.powerStatusLabel, subtitle: 'On / Off / Power state', icon: Icons.power_settings_new_rounded),
                    HomeKpiTile(title: 'Operating Mode', value: selected.operatingModeLabel, subtitle: 'Cooling controller mode', icon: Icons.hvac_rounded),
                    HomeKpiTile(title: 'Fault Summary', value: selected.faultSummaryLabel, subtitle: 'Cooling-side fault rollup', icon: Icons.error_outline_rounded),
                    HomeKpiTile(title: 'Alarm Summary', value: selected.alarmSummaryLabel, subtitle: 'Cooling-side alarm rollup', icon: Icons.warning_amber_rounded),
                    HomeKpiTile(title: 'Cooling Set Temp', value: _fmt(selected.coolingSetTempC, '°C'), subtitle: 'Configured cooling target', icon: Icons.thermostat_rounded),
                    HomeKpiTile(title: 'Heating Set Temp', value: _fmt(selected.heatingSetTempC, '°C'), subtitle: 'Configured heating target', icon: Icons.thermostat_auto_rounded),
                    HomeKpiTile(title: 'Inlet Water Temp', value: _fmt(selected.inletWaterTempC, '°C'), subtitle: 'Measured inlet temperature', icon: Icons.water_drop_rounded),
                    HomeKpiTile(title: 'Outlet Water Temp', value: _fmt(selected.outletWaterTempC, '°C'), subtitle: 'Measured outlet temperature', icon: Icons.water_drop_outlined),
                    HomeKpiTile(title: 'Inlet Pressure', value: _fmt(selected.inletWaterPressureBar, 'Bar'), subtitle: 'Measured inlet pressure', icon: Icons.speed_rounded),
                    HomeKpiTile(title: 'Outlet Pressure', value: _fmt(selected.outletWaterPressureBar, 'Bar'), subtitle: 'Measured outlet pressure', icon: Icons.speed_outlined),
                    HomeKpiTile(title: 'Outlet High Temp Alarm', value: _fmt(selected.outletHighTempAlarmValueC, '°C'), subtitle: 'Configured threshold', icon: Icons.device_thermostat_rounded),
                    HomeKpiTile(title: 'Inlet Low Pressure Alarm', value: _fmt(selected.inletLowPressureAlarmValueBar, 'Bar'), subtitle: 'Configured threshold', icon: Icons.compress_rounded),
                  ],
                ),
                const SizedBox(height: 18),
                Row(
                  children: [
                    Expanded(child: MiniTrendCard(title: '${selected.displayName} Water Temperature', points: _tempTrends[selected.sourceId] ?? const [], unit: '°C', lineColor: const Color(0xFF4B74D6))),
                    const SizedBox(width: 12),
                    Expanded(child: MiniTrendCard(title: '${selected.displayName} Water Pressure', points: _pressureTrends[selected.sourceId] ?? const [], unit: 'Bar', lineColor: const Color(0xFF2DB27D))),
                  ],
                ),
                const SizedBox(height: 18),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: _summaryBand(
                        context,
                        title: 'Active Chiller Faults',
                        items: selected.faultItems,
                        danger: true,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: _summaryBand(
                        context,
                        title: 'Active Chiller Alarms',
                        items: selected.alarmItems,
                        danger: false,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: _detailFieldCard(
                        context,
                        'Chiller Fault Fields',
                        selected.faultItems,
                        fault: true,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: _detailFieldCard(
                        context,
                        'Chiller Alarm Fields',
                        selected.alarmItems,
                        fault: false,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 18),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(18),
                    child: Text(
                      'Liquid Cooling page reads full runtime asset telemetry from /api/assets/{asset_id}/telemetry and keeps live inlet/outlet temperature and pressure trends in-memory for fast local navigation.',
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: const Color(0xFF5B6775)),
                    ),
                  ),
                ),
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

  Widget _detailFieldCard(BuildContext context, String title, List<PcsFaultItem> items, {required bool fault}) {
    final shown = items.take(18).toList();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
            const SizedBox(height: 12),
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
              Text('Showing first ${shown.length} fields out of ${items.length}.', style: Theme.of(context).textTheme.bodySmall?.copyWith(color: const Color(0xFF6C7B8A))),
          ],
        ),
      ),
    );
  }

  static String _fmt(double? value, String unit) => value == null ? '--' : '${value.toStringAsFixed(1)} $unit';
}
