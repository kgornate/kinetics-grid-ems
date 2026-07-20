import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/api/northbound_api_client.dart';
import '../../auth/models/auth_session.dart';
import '../../auth/screens/environment_select_screen.dart';
import '../../auth/services/session_store.dart';
import '../models/bms_source_snapshot.dart';
import '../models/pcs_fault_item.dart';
import '../models/source_summary.dart';
import '../utils/bms_page_builder.dart';
import '../widgets/dashboard_nav_actions.dart';
import '../widgets/home_kpi_tile.dart';
import '../widgets/mini_trend_card.dart';
import 'dashboard_shell_screen.dart';
import 'home_dashboard_screen.dart';
import 'pcs_screen.dart';
import 'liquid_cooling_screen.dart';
import 'topology_screen.dart';

class BmsScreen extends StatefulWidget {
  final AuthSession session;
  final ValueChanged<DashboardPage>? onNavigate;
  final Future<void> Function()? onLogout;

  const BmsScreen({
    super.key,
    required this.session,
    this.onNavigate,
    this.onLogout,
  });

  @override
  State<BmsScreen> createState() => _BmsScreenState();
}

class _BmsScreenState extends State<BmsScreen> {
  static const _maxTrendPoints = 24;
  static const _pollInterval = Duration(seconds: 8);

  bool _bootLoading = true;
  bool _refreshing = false;
  String? _error;
  List<SourceSummary> _sources = const [];
  List<BmsSourceSnapshot> _bmsSnapshots = const [];
  String? _selectedSourceId;

  final Map<String, List<TrendPoint>> _socTrends = {};
  final Map<String, List<TrendPoint>> _currentTrends = {};

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

  Future<void> _goHome() async {
    if (widget.onNavigate != null) {
      widget.onNavigate!(DashboardPage.home);
      return;
    }
    _timer?.cancel();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => HomeDashboardScreen(session: widget.session)),
    );
  }

  Future<void> _goTopology() async {
    if (widget.onNavigate != null) {
      widget.onNavigate!(DashboardPage.topology);
      return;
    }
    _timer?.cancel();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => TopologyScreen(session: widget.session)),
    );
  }

  Future<void> _goPcs() async {
    if (widget.onNavigate != null) {
      widget.onNavigate!(DashboardPage.pcs);
      return;
    }
    _timer?.cancel();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => PcsScreen(session: widget.session)),
    );
  }



  Future<void> _goChiller() async {
    if (widget.onNavigate != null) {
      widget.onNavigate!(DashboardPage.chiller);
      return;
    }
    _timer?.cancel();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => LiquidCoolingScreen(session: widget.session)),
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

      final snapshots = <BmsSourceSnapshot>[];
      for (final source in sourceItems) {
        final assetsJson = await api.getAssets(sourceId: source.sourceId);
        final assetItems = (assetsJson['items'] as List? ?? [])
            .whereType<Map<String, dynamic>>()
            .toList();

        Map<String, dynamic>? bmsAsset;
        for (final item in assetItems) {
          final baseAsset = item['base_asset_id']?.toString().toLowerCase() ?? '';
          final assetId = item['asset_id']?.toString().toLowerCase() ?? '';
          if (baseAsset == 'bms_1' || assetId.contains('_bms')) {
            bmsAsset = item;
            break;
          }
        }

        Map<String, dynamic>? bmsTelemetry;
        if (bmsAsset != null) {
          bmsTelemetry = await api.getAssetTelemetry(
            bmsAsset['asset_id'].toString(),
            compact: false,
            pageSize: 2000,
          );
        }

        snapshots.add(
          BmsPageBuilder.buildForSource(
            source: source,
            bmsTelemetry: bmsTelemetry,
            fallbackOnline: source.online,
          ),
        );
      }

      for (final snapshot in snapshots) {
        _appendTrend(_socTrends, snapshot.sourceId, snapshot.socPercent);
        _appendTrend(_currentTrends, snapshot.sourceId, snapshot.packCurrentA);
      }

      final selected = _selectedSourceId != null &&
              snapshots.any((e) => e.sourceId == _selectedSourceId)
          ? _selectedSourceId
          : (snapshots.isNotEmpty ? snapshots.first.sourceId : null);

      if (!mounted) return;
      setState(() {
        _sources = sourceItems;
        _bmsSnapshots = snapshots;
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
    final selected = _bmsSnapshots.where((e) => e.sourceId == _selectedSourceId).cast<BmsSourceSnapshot?>().firstWhere(
          (e) => e != null,
          orElse: () => _bmsSnapshots.isNotEmpty ? _bmsSnapshots.first : null,
        );

    final width = MediaQuery.of(context).size.width;
    final wide = width > 1320;

    return Scaffold(
      appBar: AppBar(
        title: const Text('NorthBound EMS Dashboard'),
        actions: [
          DashboardNavActions(
            currentPage: DashboardPage.bms,
            connectionLabel: '${widget.session.connection.label} • ${widget.session.displayName}',
            onHome: _goHome,
            onTopology: _goTopology,
            onPcs: _goPcs,
            onBms: () {},
            onChiller: _goChiller,
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
            else if (_error != null && selected == null)
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(18),
                  child: Text(_error!),
                ),
              )
            else if (selected != null) ...[
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Card(
                    child: Padding(
                      padding: const EdgeInsets.all(18),
                      child: Text(
                        _error!,
                        style: const TextStyle(color: Color(0xFFC53939)),
                      ),
                    ),
                  ),
                ),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                children: _bmsSnapshots.map((snapshot) {
                  final selectedChip = snapshot.sourceId == selected.sourceId;
                  return ChoiceChip(
                    label: Text(snapshot.displayName),
                    selected: selectedChip,
                    onSelected: (_) => setState(() => _selectedSourceId = snapshot.sourceId),
                  );
                }).toList(),
              ),
              const SizedBox(height: 18),
              Text(
                '${selected.displayName} · Battery Management System',
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 8),
              Text(
                '${selected.sourceId} • ${selected.host}:${selected.port}',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: const Color(0xFF6B7A8C)),
              ),
              const SizedBox(height: 16),
              GridView.count(
                crossAxisCount: wide ? 4 : 2,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                crossAxisSpacing: 12,
                mainAxisSpacing: 12,
                childAspectRatio: 1.55,
                children: [
                  HomeKpiTile(
                    title: 'SOC',
                    value: _fmt(selected.socPercent, suffix: ' %'),
                    subtitle: 'Battery cluster / pack SOC',
                    icon: Icons.battery_full_rounded,
                  ),
                  HomeKpiTile(
                    title: 'SOH',
                    value: _fmt(selected.sohPercent, suffix: ' %'),
                    subtitle: 'Battery health estimate',
                    icon: Icons.favorite_border_rounded,
                  ),
                  HomeKpiTile(
                    title: 'System Status',
                    value: selected.systemStatusLabel,
                    subtitle: 'BMS overall state',
                    icon: Icons.settings_input_component_rounded,
                  ),
                  HomeKpiTile(
                    title: 'Charge / Discharge',
                    value: selected.chargeDischargeStatusLabel,
                    subtitle: 'Derived from current / status',
                    icon: Icons.compare_arrows_rounded,
                  ),
                ],
              ),
              const SizedBox(height: 16),
              GridView.count(
                crossAxisCount: wide ? 3 : 2,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                crossAxisSpacing: 12,
                mainAxisSpacing: 12,
                childAspectRatio: 1.7,
                children: [
                  HomeKpiTile(
                    title: 'Pack Voltage',
                    value: _fmt(selected.packVoltageV, suffix: ' V'),
                    subtitle: 'Battery pack voltage',
                    icon: Icons.bolt_rounded,
                  ),
                  HomeKpiTile(
                    title: 'Pack Current',
                    value: _fmt(selected.packCurrentA, suffix: ' A'),
                    subtitle: 'Measured pack current',
                    icon: Icons.tune_rounded,
                  ),
                  HomeKpiTile(
                    title: 'Cluster Resistance',
                    value: _fmt(selected.clusterResistanceMilliOhm, suffix: ' mΩ'),
                    subtitle: 'Measured cluster internal resistance',
                    icon: Icons.speed_rounded,
                  ),
                  HomeKpiTile(
                    title: 'Max Cell Voltage',
                    value: _fmt(selected.maxCellVoltageMv, suffix: ' mV'),
                    subtitle: selected.maxCellVoltageId != null ? 'Cell ID ${selected.maxCellVoltageId}' : 'Highest detected cell voltage',
                    icon: Icons.arrow_upward_rounded,
                  ),
                  HomeKpiTile(
                    title: 'Min Cell Voltage',
                    value: _fmt(selected.minCellVoltageMv, suffix: ' mV'),
                    subtitle: selected.minCellVoltageId != null ? 'Cell ID ${selected.minCellVoltageId}' : 'Lowest detected cell voltage',
                    icon: Icons.arrow_downward_rounded,
                  ),
                  HomeKpiTile(
                    title: 'Fault Summary',
                    value: selected.faultSummaryLabel,
                    subtitle: 'Current protection / fault state',
                    icon: Icons.error_outline_rounded,
                  ),
                  HomeKpiTile(
                    title: 'Alarm Summary',
                    value: selected.alarmSummaryLabel,
                    subtitle: 'Current warning / alarm state',
                    icon: Icons.warning_amber_rounded,
                  ),
                ],
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: HomeKpiTile(
                      title: 'Max Temperature',
                      value: _fmt(selected.maxTempC, suffix: ' °C'),
                      subtitle: selected.maxTempId != null ? 'Sensor ID ${selected.maxTempId}' : 'Highest measured temperature',
                      icon: Icons.thermostat_rounded,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: HomeKpiTile(
                      title: 'Min Temperature',
                      value: _fmt(selected.minTempC, suffix: ' °C'),
                      subtitle: selected.minTempId != null ? 'Sensor ID ${selected.minTempId}' : 'Lowest measured temperature',
                      icon: Icons.ac_unit_rounded,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: HomeKpiTile(
                      title: 'Energy Charged',
                      value: _fmtDynamic(selected.totalEnergyCharged, selected.totalEnergyChargedUnit),
                      subtitle: 'Accumulated charged energy or capacity',
                      icon: Icons.trending_up_rounded,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: HomeKpiTile(
                      title: 'Energy Discharged',
                      value: _fmtDynamic(selected.totalEnergyDischarged, selected.totalEnergyDischargedUnit),
                      subtitle: 'Accumulated discharged energy or capacity',
                      icon: Icons.trending_down_rounded,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 18),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: _summaryBand(
                      context,
                      title: 'Active BMS Fault Conditions',
                      items: selected.faultItems,
                      danger: true,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: _summaryBand(
                      context,
                      title: 'Active BMS Alarm Conditions',
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
                      'BMS Fault / Protection Indicators',
                      selected.faultItems,
                      fault: true,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: _detailFieldCard(
                      context,
                      'BMS Alarm / Warning Indicators',
                      selected.alarmItems,
                      fault: false,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              _detailFieldCard(
                context,
                'BMS Protection Thresholds / Limit Settings',
                selected.thresholdItems,
                fault: false,
                maxItems: 24,
              ),
              const SizedBox(height: 18),
              Row(
                children: [
                  Expanded(
                    child: MiniTrendCard(
                      title: 'SOC Trend',
                      subtitle: 'Short in-memory live trend',
                      points: _socTrends[selected.sourceId] ?? const [],
                      valueFormatter: (v) => '${v.toStringAsFixed(1)}%',
                      minY: 0,
                      maxY: 100,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: MiniTrendCard(
                      title: 'Pack Current Trend',
                      subtitle: 'Live current movement',
                      points: _currentTrends[selected.sourceId] ?? const [],
                      valueFormatter: (v) => '${v.toStringAsFixed(1)} A',
                    ),
                  ),
                ],
              ),
            ],
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
              Text('No active ${danger ? 'fault conditions' : 'alarm conditions'}', style: TextStyle(color: accent, fontWeight: FontWeight.w700))
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
                      ? 'No dedicated protection / fault indicator fields are currently exposed or mapped from this source telemetry.'
                      : 'No dedicated alarm / warning indicator fields are currently exposed or mapped from this source telemetry.',
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
                        color: item.active
                            ? (fault ? const Color(0xFFD64545) : const Color(0xFFB7791F))
                            : const Color(0xFF5B6775),
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

  String _fmt(double? value, {required String suffix}) {
    if (value == null) return '--';
    return '${value.toStringAsFixed(1)}$suffix';
  }

  String _fmtDynamic(double? value, String? unit) {
    if (value == null) return '--';
    final suffix = (unit == null || unit.isEmpty) ? '' : ' $unit';
    return '${value.toStringAsFixed(1)}$suffix';
  }
}
