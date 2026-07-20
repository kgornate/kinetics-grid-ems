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
import '../widgets/system_status_panel.dart';
import 'bms_screen.dart';
import 'liquid_cooling_screen.dart';
import 'pcs_screen.dart';
import 'topology_screen.dart';

class HomeDashboardScreen extends StatefulWidget {
  final AuthSession session;
  final ValueChanged<DashboardPage>? onNavigate;
  final Future<void> Function()? onLogout;

  const HomeDashboardScreen({
    super.key,
    required this.session,
    this.onNavigate,
    this.onLogout,
  });

  @override
  State<HomeDashboardScreen> createState() => _HomeDashboardScreenState();
}

class _HomeDashboardScreenState extends State<HomeDashboardScreen> {
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

  Future<void> _goTopology() async {
    if (widget.onNavigate != null) {
      widget.onNavigate!(DashboardPage.topology);
      return;
    }
    _timer?.cancel();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(
        builder: (_) => TopologyScreen(session: widget.session),
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
            currentPage: DashboardPage.home,
            connectionLabel: '${widget.session.connection.label} • ${widget.session.displayName}',
            onHome: () {},
            onTopology: _goTopology,
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
                'Home Overview',
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
                    subtitle: 'Average of available EMS battery SOC values',
                    icon: Icons.battery_full_rounded,
                  ),
                  HomeKpiTile(
                    title: 'Site Active Power',
                    value: summary.siteActivePowerKw != null
                        ? '${summary.siteActivePowerKw!.toStringAsFixed(1)} kW'
                        : '--',
                    subtitle: 'Sum of source-level active power',
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
                    subtitle: 'Rolled up from both fire protection assets',
                    icon: Icons.local_fire_department_rounded,
                  ),
                ],
              ),
              const SizedBox(height: 18),
              Text(
                'External EMS Sources',
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
              ),
              const SizedBox(height: 14),
              GridView.count(
                crossAxisCount: wide ? 2 : 1,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                crossAxisSpacing: 12,
                mainAxisSpacing: 12,
                childAspectRatio: wide ? 1.85 : 1.6,
                children: summary.sources
                    .map((s) => SourceSummaryCard(source: s))
                    .toList(),
              ),
              const SizedBox(height: 18),
              if (wide)
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      flex: 2,
                      child: _topologyPreview(context),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: SystemStatusPanel(sources: summary.sources),
                    ),
                  ],
                )
              else ...[
                _topologyPreview(context),
                const SizedBox(height: 12),
                SystemStatusPanel(sources: summary.sources),
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
                        title: 'Grid / Power Trend',
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
                  title: 'Grid / Power Trend',
                  points: _powerTrend,
                  unit: 'kW',
                  lineColor: const Color(0xFF4A76D1),
                ),
              ],
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

  Widget _topologyPreview(BuildContext context) {
    final summary = _summary;
    return Card(
      child: SizedBox(
        height: 340,
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      'Site Home / Topology Preview',
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.w700,
                          ),
                    ),
                  ),
                  FilledButton.tonalIcon(
                    onPressed: _goTopology,
                    icon: const Icon(Icons.account_tree_outlined),
                    label: const Text('Open Topology'),
                  ),
                  const SizedBox(width: 8),
                  FilledButton.tonalIcon(
                    onPressed: _goPcs,
                    icon: const Icon(Icons.electrical_services_outlined),
                    label: const Text('Open PCS'),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Text(
                'Important site-level summary only. Detailed PCS, BMS, Fire, and Cooling pages will come next.',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: const Color(0xFF6C7B8A),
                    ),
              ),
              const SizedBox(height: 14),
              Expanded(
                child: Container(
                  decoration: BoxDecoration(
                    color: const Color(0xFFF8FAFD),
                    borderRadius: BorderRadius.circular(18),
                    border: Border.all(color: const Color(0xFFE6EBF2)),
                  ),
                  child: InkWell(
                    onTap: _goTopology,
                    borderRadius: BorderRadius.circular(18),
                    child: Padding(
                      padding: const EdgeInsets.all(18),
                      child: summary == null
                          ? const Center(
                              child: Text(
                                'Open topology page',
                                style: TextStyle(
                                  color: Color(0xFF6C7B8A),
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            )
                          : Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    _miniNode(
                                      icon: Icons.power,
                                      title: 'Grid',
                                      subtitle: summary.siteActivePowerKw != null
                                          ? '${summary.siteActivePowerKw!.toStringAsFixed(1)} kW'
                                          : '--',
                                    ),
                                    const Spacer(),
                                    _miniNode(
                                      icon: Icons.apartment_rounded,
                                      title: 'Load',
                                      subtitle: summary.fireAlarmActive ? 'Alarm' : 'Normal',
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 12),
                                Expanded(
                                  child: Center(
                                    child: FittedBox(
                                      fit: BoxFit.scaleDown,
                                      child: Container(
                                        width: 118,
                                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                                        decoration: BoxDecoration(
                                          color: const Color(0xFF4A76D1),
                                          borderRadius: BorderRadius.circular(18),
                                        ),
                                        child: Column(
                                          mainAxisSize: MainAxisSize.min,
                                          children: [
                                            const Icon(Icons.hub_rounded, color: Colors.white, size: 22),
                                            const SizedBox(height: 6),
                                            const Text(
                                              'Site Bus',
                                              style: TextStyle(
                                                color: Colors.white,
                                                fontWeight: FontWeight.w800,
                                              ),
                                            ),
                                            const SizedBox(height: 4),
                                            Text(
                                              summary.overallSoc != null
                                                  ? '${summary.overallSoc!.toStringAsFixed(1)} %'
                                                  : '--',
                                              style: const TextStyle(
                                                color: Colors.white,
                                                fontWeight: FontWeight.w700,
                                              ),
                                            ),
                                          ],
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                                Row(
                                  children: [
                                    Expanded(
                                      child: _sourcePreviewChip(
                                        summary.sources.isNotEmpty
                                            ? summary.sources[0].shortTitle
                                            : 'EMS 1',
                                      ),
                                    ),
                                    const SizedBox(width: 12),
                                    Expanded(
                                      child: _sourcePreviewChip(
                                        summary.sources.length > 1
                                            ? summary.sources[1].shortTitle
                                            : 'EMS 2',
                                      ),
                                    ),
                                  ],
                                ),
                              ],
                            ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _miniNode({
    required IconData icon,
    required String title,
    required String subtitle,
  }) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE6EBF2)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 18, color: const Color(0xFF4A76D1)),
          const SizedBox(width: 8),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(
                  color: Color(0xFF6C7B8A),
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
              Text(
                subtitle,
                style: const TextStyle(fontWeight: FontWeight.w800),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _sourcePreviewChip(String title) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFFEAF8F1),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFCFECDC)),
      ),
      child: Center(
        child: Text(
          title,
          style: const TextStyle(
            fontWeight: FontWeight.w700,
            color: Color(0xFF228B5A),
          ),
        ),
      ),
    );
  }
}
