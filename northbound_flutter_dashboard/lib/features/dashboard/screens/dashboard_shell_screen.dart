import 'package:flutter/material.dart';

import '../../auth/models/auth_session.dart';
import '../../auth/screens/environment_select_screen.dart';
import '../../auth/services/session_store.dart';
import '../widgets/dashboard_nav_actions.dart';
import 'bms_screen.dart';
import 'dehumidifier_screen.dart';
import 'ems_system_screen.dart';
import 'fire_screen.dart';
import 'fast_bess_historian_screen.dart';
import 'home_dashboard_screen.dart';
import 'liquid_cooling_screen.dart';
import 'pcs_screen.dart';
import 'strategy_command_screen.dart';
import 'topology_screen.dart';
import 'utility_meter_screen.dart';

class DashboardShellScreen extends StatefulWidget {
  final AuthSession session;
  final DashboardPage initialPage;

  const DashboardShellScreen({
    super.key,
    required this.session,
    this.initialPage = DashboardPage.home,
  });

  @override
  State<DashboardShellScreen> createState() => _DashboardShellScreenState();
}

class _DashboardShellScreenState extends State<DashboardShellScreen> {
  static const List<DashboardPage> _pageOrder = <DashboardPage>[
    DashboardPage.home,
    DashboardPage.topology,
    DashboardPage.pcs,
    DashboardPage.bms,
    DashboardPage.historian,
    DashboardPage.chiller,
    DashboardPage.dehumidifier,
    DashboardPage.fire,
    DashboardPage.utilityMeter,
    DashboardPage.emsSystem,
    DashboardPage.strategy,
  ];

  late DashboardPage _currentPage;

  // Phase F2.1 navigation behavior:
  // Keep pages alive after first load so switching back to PCS/BMS/Historian
  // does not rebuild the whole screen and refetch everything from zero.
  // This is intentionally a lazy cache: only pages visited by the user are
  // created. Unvisited pages stay as lightweight placeholders.
  final Map<DashboardPage, Widget> _pageCache = <DashboardPage, Widget>{};

  @override
  void initState() {
    super.initState();
    _currentPage = widget.initialPage;
    _ensurePage(_currentPage);
  }

  void _goToPage(DashboardPage page) {
    if (_currentPage == page) return;
    setState(() {
      _currentPage = page;
      _ensurePage(page);
    });
  }

  Future<void> _logout() async {
    await SessionStore().clear();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const EnvironmentSelectScreen()),
      (route) => false,
    );
  }

  void _ensurePage(DashboardPage page) {
    _pageCache.putIfAbsent(page, () => _buildPage(page));
  }

  Widget _buildPage(DashboardPage page) {
    return switch (page) {
      DashboardPage.home => HomeDashboardScreen(
          key: const PageStorageKey<String>('dashboard-home'),
          session: widget.session,
          onNavigate: _goToPage,
          onLogout: _logout,
        ),
      DashboardPage.topology => TopologyScreen(
          key: const PageStorageKey<String>('dashboard-topology'),
          session: widget.session,
          onNavigate: _goToPage,
          onLogout: _logout,
        ),
      DashboardPage.pcs => PcsScreen(
          key: const PageStorageKey<String>('dashboard-pcs'),
          session: widget.session,
          onNavigate: _goToPage,
          onLogout: _logout,
        ),
      DashboardPage.bms => BmsScreen(
          key: const PageStorageKey<String>('dashboard-bms'),
          session: widget.session,
          onNavigate: _goToPage,
          onLogout: _logout,
        ),
      DashboardPage.historian => FastBessHistorianScreen(
          key: const PageStorageKey<String>('dashboard-historian'),
          session: widget.session,
          onNavigate: _goToPage,
          onLogout: _logout,
        ),
      DashboardPage.chiller => LiquidCoolingScreen(
          key: const PageStorageKey<String>('dashboard-chiller'),
          session: widget.session,
          onNavigate: _goToPage,
          onLogout: _logout,
        ),
      DashboardPage.dehumidifier => DehumidifierScreen(
          key: const PageStorageKey<String>('dashboard-dehumidifier'),
          session: widget.session,
          onNavigate: _goToPage,
          onLogout: _logout,
        ),
      DashboardPage.fire => FireScreen(
          key: const PageStorageKey<String>('dashboard-fire'),
          session: widget.session,
          onNavigate: _goToPage,
          onLogout: _logout,
        ),
      DashboardPage.utilityMeter => UtilityMeterScreen(
          key: const PageStorageKey<String>('dashboard-utility-meter'),
          session: widget.session,
          onNavigate: _goToPage,
          onLogout: _logout,
        ),
      DashboardPage.emsSystem => EmsSystemScreen(
          key: const PageStorageKey<String>('dashboard-ems-system'),
          session: widget.session,
          onNavigate: _goToPage,
          onLogout: _logout,
        ),
      DashboardPage.strategy => StrategyCommandScreen(
          key: const PageStorageKey<String>('dashboard-strategy'),
          session: widget.session,
          onNavigate: _goToPage,
          onLogout: _logout,
        ),
    };
  }

  @override
  Widget build(BuildContext context) {
    final currentIndex = _pageOrder.indexOf(_currentPage);

    return IndexedStack(
      index: currentIndex < 0 ? 0 : currentIndex,
      children: _pageOrder.map((page) {
        return _pageCache[page] ?? const SizedBox.shrink();
      }).toList(growable: false),
    );
  }
}
