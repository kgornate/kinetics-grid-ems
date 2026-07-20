import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/api/northbound_api_client.dart';
import '../../auth/models/auth_session.dart';
import '../../auth/screens/environment_select_screen.dart';
import '../../auth/services/session_store.dart';
import '../models/site_dashboard_summary.dart';
import '../models/source_summary.dart';
import '../utils/dashboard_aggregator.dart';
import '../widgets/dashboard_nav_actions.dart';
import '../widgets/home_kpi_tile.dart';
import '../widgets/mini_trend_card.dart';
import '../widgets/source_summary_card.dart';
import '../widgets/topology_diagram_card.dart';
import 'bms_screen.dart';
import 'liquid_cooling_screen.dart';
import 'home_dashboard_screen.dart';
import 'pcs_screen.dart';

class TopologyScreen extends StatefulWidget {
  final AuthSession session;
  final ValueChanged<DashboardPage>? onNavigate;
  final Future<void> Function()? onLogout;

  const TopologyScreen({
    super.key,
    required this.session,
    this.onNavigate,
    this.onLogout,
  });

  @override
  State<TopologyScreen> createState() => _TopologyScreenState();
}

class _TopologyScreenState extends State<TopologyScreen> {
  static const _maxTrendPoints = 24;
  static const _pollInterval = Duration(seconds: 8);

  bool _bootLoading = true;
  bool _refreshing = false;
  String? _error;
  SiteDashboardSummary? _summary;
  List<SourceSummary> _sources = const [];
  final List<TrendPoint> _socTrend = [];
  final List<TrendPoint> _powerTrend = [];
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
      MaterialPageRoute(
        builder: (_) => HomeDashboardScreen(session: widget.session),
      ),
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
      MaterialPageRoute(
        builder: (_) => PcsScreen(session: widget.session),
      ),
    );
  }


  Future<void> _goBms() async {
    if (widget.onNavigate != null) {
      widget.onNavigate!(DashboardPage.bms);
      return;
    }
    _timer?.cancel();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(
        builder: (_) => BmsScreen(session: widget.session),
      ),
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
    MaterialPageRoute(
      builder: (_) => LiquidCoolingScreen(session: widget.session),
    ),
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

      final health = await api.getHealth();
      final sourcesJson = await api.getSourcesSummary();
      final keySignals = await api.getKeySignals();
      final alarms = await api.getAlarms();

      final sourceItems = (sourcesJson['items'] as List? ?? [])
          .whereType<Map<String, dynamic>>()
          .map(SourceSummary.fromJson)
          .toList();

      final summary = DashboardAggregator.build(
        health: health,
        sources: sourceItems,
        keySignals: keySignals,
        alarmCount: (alarms['active_count'] as num?)?.toInt() ?? 0,
      );

      _appendTrend(_socTrend, summary.overallSoc);
      _appendTrend(_powerTrend, summary.siteActivePowerKw);

      if (!mounted) return;
      setState(() {
        _sources = sourceItems;
        _summary = summary;
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

  void _appendTrend(List<TrendPoint> buffer, double? value) {
    if (value == null) return;
    buffer.add(TrendPoint(timestamp: DateTime.now(), value: value));
    if (buffer.length > _maxTrendPoints) {
      buffer.removeRange(0, buffer.length - _maxTrendPoints);
    }
  }

  @override
  Widget build(BuildContext context) {
    final summary = _summary;
    final width = MediaQuery.of(context).size.width;
    final wide = width > 1320;

    return Scaffold(
      appBar: AppBar(
        title: const Text('NorthBound EMS Dashboard'),
        actions: [
          DashboardNavActions(
            currentPage: DashboardPage.topology,
            connectionLabel: '${widget.session.connection.label} • ${widget.session.displayName}',
            onHome: _goHome,
            onTopology: () {},
            onPcs: _goPcs,
            onBms: _goBms,
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
            if (_bootLoading && summary == null)
              const Padding(
                padding: EdgeInsets.all(40),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (_error != null && summary == null)
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(18),
                  child: Text(_error!),
                ),
              )
            else if (summary != null) ...[
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
                spacing: 12,
                runSpacing: 12,
                children: [
                  _pill('Gateway ${summary.gatewayHealthy ? 'OK' : 'Check'}'),
                  _pill(widget.session.isInternal ? 'Internal mode' : 'Customer mode'),
                  _pill('Sources: ${summary.sourceCount}'),
                  _pill('Alarms: ${summary.alarmCount}'),
                  _pill('Storage: ${summary.storageEnabled ? 'enabled' : 'disabled'}'),
                  _pill('Mode: ${summary.gatewayMode}'),
                ],
              ),
              const SizedBox(height: 18),
              Text(
                'Topology Overview',
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
              ),
              const SizedBox(height: 14),
              GridView.count(
                crossAxisCount: wide ? 4 : 2,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                crossAxisSpacing: 12,
                mainAxisSpacing: 12,
                childAspectRatio: 1.6,
                children: [
                  HomeKpiTile(
                    title: 'Overall SOC',
                    value: summary.overallSoc != null
                        ? '${summary.overallSoc!.toStringAsFixed(1)} %'
                        : '--',
                    subtitle: 'Combined EMS battery average',
                    icon: Icons.battery_full_rounded,
                  ),
                  HomeKpiTile(
                    title: 'Site Active Power',
                    value: summary.siteActivePowerKw != null
                        ? '${summary.siteActivePowerKw!.toStringAsFixed(1)} kW'
                        : '--',
                    subtitle: 'Total site exchange estimate',
                    icon: Icons.electric_bolt_rounded,
                  ),
                  HomeKpiTile(
                    title: 'BESS Status',
                    value: summary.bessFleetLabel,
                    subtitle: 'External EMS BESS units commanded ON',
                    icon: Icons.power_settings_new_rounded,
                  ),
                  HomeKpiTile(
                    title: 'Fire Alarm',
                    value: summary.fireAlarmActive ? 'Active' : 'Normal',
                    subtitle: 'Rolled up from both fire assets',
                    icon: Icons.local_fire_department_rounded,
                  ),
                ],
              ),
              const SizedBox(height: 18),
              if (wide)
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      flex: 2,
                      child: SizedBox(
                        height: 560,
                        child: TopologyDiagramCard(summary: summary),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: SizedBox(
                        height: 560,
                        child: Card(
                          child: Padding(
                            padding: const EdgeInsets.all(18),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Expanded(
                                      child: Text(
                                        'Source Breakdown',
                                        style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                              fontWeight: FontWeight.w700,
                                            ),
                                      ),
                                    ),
                                    FilledButton.tonalIcon(
                                      onPressed: _goPcs,
                                      icon: const Icon(Icons.electrical_services_outlined),
                                      label: const Text('Open PCS'),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 14),
                                Expanded(
                                  child: ListView.separated(
                                    itemCount: summary.sources.length,
                                    separatorBuilder: (_, __) => const SizedBox(height: 12),
                                    itemBuilder: (context, index) {
                                      return SourceSummaryCard(source: summary.sources[index]);
                                    },
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                )
              else ...[
                SizedBox(
                  height: 560,
                  child: TopologyDiagramCard(summary: summary),
                ),
                const SizedBox(height: 12),
                FilledButton.tonalIcon(
                  onPressed: _goPcs,
                  icon: const Icon(Icons.electrical_services_outlined),
                  label: const Text('Open PCS'),
                ),
                const SizedBox(height: 12),
                ...summary.sources.map(
                  (s) => Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: SourceSummaryCard(source: s),
                  ),
                ),
              ],
              const SizedBox(height: 18),
              if (wide)
                Row(
                  children: [
                    Expanded(
                      child: MiniTrendCard(
                        title: 'SOC Trend',
                        points: _socTrend,
                        unit: '%',
                        lineColor: const Color(0xFF36B37E),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: MiniTrendCard(
                        title: 'Site Power Trend',
                        points: _powerTrend,
                        unit: 'kW',
                        lineColor: const Color(0xFF4A76D1),
                      ),
                    ),
                  ],
                )
              else ...[
                MiniTrendCard(
                  title: 'SOC Trend',
                  points: _socTrend,
                  unit: '%',
                  lineColor: const Color(0xFF36B37E),
                ),
                const SizedBox(height: 12),
                MiniTrendCard(
                  title: 'Site Power Trend',
                  points: _powerTrend,
                  unit: 'kW',
                  lineColor: const Color(0xFF4A76D1),
                ),
              ],
              const SizedBox(height: 18),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(18),
                  child: Text(
                    'Topology page is a live supervisory overview. Detailed PCS, BMS, Liquid Cooling, and Fire pages build next on top of the same authenticated gateway APIs.',
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: const Color(0xFF425466),
                        ),
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _pill(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE6EBF2)),
      ),
      child: Text(
        label,
        style: const TextStyle(fontWeight: FontWeight.w600),
      ),
    );
  }
}
