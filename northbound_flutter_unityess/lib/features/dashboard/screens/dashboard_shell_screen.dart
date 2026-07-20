import 'package:flutter/material.dart';

import '../../auth/models/auth_session.dart';
import '../../auth/screens/environment_select_screen.dart';
import '../../auth/services/session_store.dart';
import '../widgets/dashboard_nav_actions.dart';
import 'bms_screen.dart';
import 'home_dashboard_screen.dart';
import 'liquid_cooling_screen.dart';
import 'pcs_screen.dart';
import 'topology_screen.dart';

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
  late DashboardPage _currentPage;
  late final Widget _homePage;
  late final Widget _topologyPage;
  late final Widget _pcsPage;
  late final Widget _bmsPage;
  late final Widget _chillerPage;

  @override
  void initState() {
    super.initState();
    _currentPage = widget.initialPage;

    _homePage = HomeDashboardScreen(session: widget.session, onNavigate: _goToPage, onLogout: _logout);
    _topologyPage = TopologyScreen(session: widget.session, onNavigate: _goToPage, onLogout: _logout);
    _pcsPage = PcsScreen(session: widget.session, onNavigate: _goToPage, onLogout: _logout);
    _bmsPage = BmsScreen(session: widget.session, onNavigate: _goToPage, onLogout: _logout);
    _chillerPage = LiquidCoolingScreen(session: widget.session, onNavigate: _goToPage, onLogout: _logout);
  }

  void _goToPage(DashboardPage page) {
    if (_currentPage == page) return;
    setState(() => _currentPage = page);
  }

  Future<void> _logout() async {
    await SessionStore().clear();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const EnvironmentSelectScreen()),
      (route) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    final index = switch (_currentPage) {
      DashboardPage.home => 0,
      DashboardPage.topology => 1,
      DashboardPage.pcs => 2,
      DashboardPage.bms => 3,
      DashboardPage.chiller => 4,
    };

    return IndexedStack(
      index: index,
      children: [_homePage, _topologyPage, _pcsPage, _bmsPage, _chillerPage],
    );
  }
}
