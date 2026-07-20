import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/api/northbound_api_client.dart';
import '../../auth/models/auth_session.dart';
import '../../auth/screens/environment_select_screen.dart';
import '../../auth/services/session_store.dart';
import '../models/pcs_fault_item.dart';
import '../models/pcs_source_snapshot.dart';
import '../models/source_summary.dart';
import '../utils/pcs_page_builder.dart';
import '../widgets/dashboard_nav_actions.dart';
import '../widgets/home_kpi_tile.dart';
import '../widgets/mini_trend_card.dart';
import 'bms_screen.dart';
import 'home_dashboard_screen.dart';
import 'liquid_cooling_screen.dart';
import 'topology_screen.dart';

class PcsScreen extends StatefulWidget {
  final AuthSession session;
  final ValueChanged<DashboardPage>? onNavigate;
  final Future<void> Function()? onLogout;

  const PcsScreen({
    super.key,
    required this.session,
    this.onNavigate,
    this.onLogout,
  });

  @override
  State<PcsScreen> createState() => _PcsScreenState();
}

class _PcsScreenState extends State<PcsScreen> {
  static const _maxTrendPoints = 24;
  static const _pollInterval = Duration(seconds: 8);

  bool _bootLoading = true;
  bool _refreshing = false;
  String? _error;
  List<SourceSummary> _sources = const [];
  List<PcsSourceSnapshot> _pcsSnapshots = const [];
  String? _selectedSourceId;

  final Map<String, List<TrendPoint>> _powerTrends = {};
  final Map<String, List<TrendPoint>> _dcVoltageTrends = {};

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
        return;
      case DashboardPage.bms:
        target = BmsScreen(session: widget.session);
        break;
      case DashboardPage.chiller:
        target = LiquidCoolingScreen(session: widget.session);
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
      final api = NorthboundApiClient(baseUrl: widget.session.connection.baseUrl, token: widget.session.accessToken);
      final sourcesJson = await api.getSourcesSummary();
      final sourceItems = (sourcesJson['items'] as List? ?? [])
          .whereType<Map<String, dynamic>>()
          .map(SourceSummary.fromJson)
          .toList();

      final snapshots = <PcsSourceSnapshot>[];
      for (final source in sourceItems) {
        final assetsJson = await api.getAssets(sourceId: source.sourceId);
        final assetItems = (assetsJson['items'] as List? ?? []).whereType<Map<String, dynamic>>().toList();

        Map<String, dynamic>? findAsset(String baseAssetId, String containsKey) {
          for (final item in assetItems) {
            final baseAsset = item['base_asset_id']?.toString().toLowerCase() ?? '';
            final assetId = item['asset_id']?.toString().toLowerCase() ?? '';
            if (baseAsset == baseAssetId.toLowerCase() || assetId.contains(containsKey)) {
              return item;
            }
          }
          return null;
        }

        final pcsAsset = findAsset('pcs_1', '_pcs');
        final emsAsset = findAsset('ems_system', '_ems_system');

        Map<String, dynamic>? pcsTelemetry;
        Map<String, dynamic>? emsTelemetry;
        if (pcsAsset != null) {
          pcsTelemetry = await api.getAssetTelemetry(pcsAsset['asset_id'].toString(), compact: true, pageSize: 500);
        }
        if (emsAsset != null) {
          emsTelemetry = await api.getAssetTelemetry(emsAsset['asset_id'].toString(), compact: true, pageSize: 500);
        }

        final snapshot = PcsPageBuilder.buildForSource(
          source: source,
          pcsTelemetry: pcsTelemetry,
          emsTelemetry: emsTelemetry,
          fallbackOnline: source.online,
        );
        snapshots.add(snapshot);
        _appendTrend(_powerTrends, snapshot.sourceId, snapshot.activePowerKw);
        _appendTrend(_dcVoltageTrends, snapshot.sourceId, snapshot.dcVoltageV);
      }

      final selected = _selectedSourceId != null && snapshots.any((e) => e.sourceId == _selectedSourceId)
          ? _selectedSourceId
          : (snapshots.isNotEmpty ? snapshots.first.sourceId : null);

      if (!mounted) return;
      setState(() {
        _sources = sourceItems;
        _pcsSnapshots = snapshots;
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
    final selected = _pcsSnapshots
        .where((e) => e.sourceId == _selectedSourceId)
        .cast<PcsSourceSnapshot?>()
        .firstWhere((e) => e != null, orElse: () => _pcsSnapshots.isNotEmpty ? _pcsSnapshots.first : null);

    final width = MediaQuery.of(context).size.width;
    final wide = width > 1320;

    return Scaffold(
      appBar: AppBar(
        title: const Text('NorthBound EMS Dashboard'),
        actions: [
          DashboardNavActions(
            currentPage: DashboardPage.pcs,
            connectionLabel: '${widget.session.connection.label} • ${widget.session.displayName}',
            onHome: () => _go(DashboardPage.home),
            onTopology: () => _go(DashboardPage.topology),
            onPcs: () {},
            onBms: () => _go(DashboardPage.bms),
            onChiller: () => _go(DashboardPage.chiller),
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
              Text('PCS Overview', style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700)),
              const SizedBox(height: 14),
              Wrap(
                spacing: 12,
                runSpacing: 12,
                children: _pcsSnapshots.map((snapshot) => ChoiceChip(
                  label: Text(snapshot.displayName),
                  selected: snapshot.sourceId == _selectedSourceId,
                  onSelected: (_) => setState(() => _selectedSourceId = snapshot.sourceId),
                )).toList(),
              ),
              const SizedBox(height: 18),
              if (selected == null)
                const Card(child: Padding(padding: EdgeInsets.all(18), child: Text('No PCS data available.')))
              else ...[
                _pcsHeaderCard(context, selected),
                const SizedBox(height: 18),
                GridView.count(
                  crossAxisCount: wide ? 4 : 2,
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  crossAxisSpacing: 12,
                  mainAxisSpacing: 12,
                  childAspectRatio: 1.55,
                  children: [
                    HomeKpiTile(title: 'Running Status', value: selected.runningStatusLabel, subtitle: '${selected.displayName} PCS state', icon: Icons.power_settings_new_rounded),
                    HomeKpiTile(title: 'Charge / Discharge', value: selected.chargeDischargeLabel, subtitle: 'Derived from active power', icon: Icons.sync_alt_rounded),
                    HomeKpiTile(title: 'Active Power', value: _fmt(selected.activePowerKw, 'kW'), subtitle: 'AC-side active power', icon: Icons.electric_bolt_rounded),
                    HomeKpiTile(title: 'DC Power', value: _fmt(selected.dcPowerKw, 'kW'), subtitle: 'Battery-side power', icon: Icons.battery_charging_full_rounded),
                    HomeKpiTile(title: 'AC Voltage', value: _fmt(selected.acVoltageV, 'V'), subtitle: 'Average of available phase voltages', icon: Icons.bolt_rounded),
                    HomeKpiTile(title: 'AC Current', value: _fmt(selected.acCurrentA, 'A'), subtitle: 'Average of available phase currents', icon: Icons.multiline_chart_rounded),
                    HomeKpiTile(title: 'Grid Frequency', value: _fmt(selected.gridFrequencyHz, 'Hz'), subtitle: 'Grid-following frequency feedback', icon: Icons.waves_rounded),
                    HomeKpiTile(title: 'DC Voltage', value: _fmt(selected.dcVoltageV, 'V'), subtitle: 'Battery/DC link voltage', icon: Icons.battery_6_bar_rounded),
                    HomeKpiTile(title: 'Grid Mode', value: selected.gridModeLabel, subtitle: 'On-grid / Off-grid / VSG', icon: Icons.hub_rounded),
                    HomeKpiTile(title: 'Operating Mode', value: selected.operatingModeLabel, subtitle: 'PCS work or operation mode', icon: Icons.settings_suggest_rounded),
                    HomeKpiTile(title: 'Fault Summary', value: selected.faultSummaryLabel, subtitle: 'Derived from PCS fault signals', icon: Icons.error_outline_rounded),
                    HomeKpiTile(title: 'Alarm Summary', value: selected.alarmSummaryLabel, subtitle: 'Derived from PCS alarm/warning signals', icon: Icons.notification_important_rounded),
                  ],
                ),
                const SizedBox(height: 18),
                _summaryBand(context, title: 'Active Faults', items: selected.activeFaultItems, danger: true),
                const SizedBox(height: 12),
                _summaryBand(context, title: 'Active Alarms', items: selected.activeAlarmItems, danger: false),
                const SizedBox(height: 18),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(child: _detailFieldCard(context, 'Fault Fields', selected.faultItems, fault: true)),
                    const SizedBox(width: 12),
                    Expanded(child: _detailFieldCard(context, 'Alarm Fields', selected.alarmItems, fault: false)),
                  ],
                ),
                const SizedBox(height: 18),
                Row(
                  children: [
                    Expanded(child: MiniTrendCard(title: '${selected.displayName} PCS Active Power', points: _powerTrends[selected.sourceId] ?? const [], unit: 'kW', lineColor: const Color(0xFF4B74D6))),
                    const SizedBox(width: 12),
                    Expanded(child: MiniTrendCard(title: '${selected.displayName} DC Voltage', points: _dcVoltageTrends[selected.sourceId] ?? const [], unit: 'V', lineColor: const Color(0xFF2DB27D))),
                  ],
                ),
                const SizedBox(height: 18),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(18),
                    child: Text(
                      'PCS page now reads full asset telemetry from /api/assets/{asset_id}/telemetry and displays detailed fault/alarm fields in addition to summary states. Key dashboard signals stay on compact endpoints, while detail pages use full runtime asset telemetry.',
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

  Widget _pcsHeaderCard(BuildContext context, PcsSourceSnapshot snapshot) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(snapshot.displayName, style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700)),
            const SizedBox(height: 4),
            Text('${snapshot.sourceId} • ${snapshot.host}:${snapshot.port}', style: Theme.of(context).textTheme.bodySmall?.copyWith(color: const Color(0xFF6C7B8A))),
          ],
        ),
      ),
    );
  }

  Widget _summaryBand(BuildContext context, {required String title, required List<PcsFaultItem> items, required bool danger}) {
    final activeItems = items.where((e) => e.active).toList();
    final baseColor = danger ? const Color(0xFFFDECEC) : const Color(0xFFFFF7E6);
    final accent = danger ? const Color(0xFFD64545) : const Color(0xFFB7791F);
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
                children: activeItems.map((item) => Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: accent.withOpacity(0.2)),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
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
    final shown = items.take(16).toList();
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
                  Expanded(
                    child: Text(item.displayName, style: const TextStyle(fontWeight: FontWeight.w600)),
                  ),
                  Text(item.stateLabel, style: TextStyle(fontWeight: FontWeight.w700, color: item.active ? (fault ? const Color(0xFFD64545) : const Color(0xFFB7791F)) : const Color(0xFF5B6775))),
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

  static String _fmt(double? value, String unit) => value == null ? '--' : '${value.toStringAsFixed(unit == 'Hz' ? 2 : 1)} $unit';
}
