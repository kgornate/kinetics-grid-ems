import 'package:flutter/material.dart';

import '../core/state/gateway_controller.dart';
import '../widgets/common_widgets.dart';
import 'alarms_screen.dart';
import 'bau_screen.dart';
import 'control_sequence_screen.dart';
import 'dashboard_screen.dart';
import 'diagnostics_screen.dart';
import 'environment_screen.dart';
import 'historian_screen.dart';
import 'pcs_screen.dart';
import 'racks_screen.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key, required this.controller});

  final GatewayController controller;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  List<NavigationDestination> get _destinations => <NavigationDestination>[
        const NavigationDestination(icon: Icon(Icons.dashboard_outlined), selectedIcon: Icon(Icons.dashboard), label: 'Overview'),
        const NavigationDestination(icon: Icon(Icons.battery_charging_full_outlined), selectedIcon: Icon(Icons.battery_charging_full), label: 'BAU'),
        const NavigationDestination(icon: Icon(Icons.view_column_outlined), selectedIcon: Icon(Icons.view_column), label: 'Racks'),
        const NavigationDestination(icon: Icon(Icons.ac_unit_outlined), selectedIcon: Icon(Icons.ac_unit), label: 'Environment'),
        const NavigationDestination(icon: Icon(Icons.power_outlined), selectedIcon: Icon(Icons.power), label: 'PCS'),
        if (widget.controller.isInternal)
          const NavigationDestination(icon: Icon(Icons.account_tree_outlined), selectedIcon: Icon(Icons.account_tree), label: 'Control'),
        const NavigationDestination(icon: Icon(Icons.warning_amber_outlined), selectedIcon: Icon(Icons.warning_amber), label: 'Alarms'),
        const NavigationDestination(icon: Icon(Icons.timeline_outlined), selectedIcon: Icon(Icons.timeline), label: 'Historian'),
        const NavigationDestination(icon: Icon(Icons.monitor_heart_outlined), selectedIcon: Icon(Icons.monitor_heart), label: 'Diagnostics'),
      ];


  bool _isControlDestination(int index) {
    final destinations = _destinations;
    return index >= 0 &&
        index < destinations.length &&
        destinations[index].label == 'Control';
  }

  void _selectDestination(int value) {
    final showControl = _isControlDestination(value);
    setState(() => _index = value);
    if (showControl) {
      widget.controller.refreshControlCapabilities(silent: true);
      widget.controller.startControlPolling();
    } else {
      widget.controller.stopControlPolling();
    }
  }

  @override
  void dispose() {
    widget.controller.stopControlPolling();
    super.dispose();
  }

  List<Widget> get _screens {
    final bank = widget.controller.plant.bank;
    return <Widget>[
      DashboardScreen(controller: widget.controller),
      bank == null
          ? const Center(child: Text('No BAU/bank snapshot received yet.'))
          : BauScreen(controller: widget.controller),
      RacksScreen(controller: widget.controller),
      EnvironmentScreen(controller: widget.controller),
      PcsScreen(controller: widget.controller),
      if (widget.controller.isInternal)
        ControlSequenceScreen(controller: widget.controller),
      AlarmsScreen(controller: widget.controller),
      HistorianScreen(controller: widget.controller),
      DiagnosticsScreen(controller: widget.controller),
    ];
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final wide = constraints.maxWidth >= 960;
        final destinations = _destinations;
        final screens = _screens;
        final safeIndex = _index.clamp(0, screens.length - 1);
        final body = IndexedStack(index: safeIndex, children: screens);
        return Scaffold(
          appBar: AppBar(
            title: Text('Kinetics Gateway - ${destinations[safeIndex].label}'),
            actions: [
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 10),
                child: StatusPill(
                  label: widget.controller.wsConnected ? 'Live' : 'REST only',
                  good: widget.controller.wsConnected || widget.controller.restConnected,
                  icon: widget.controller.wsConnected ? Icons.sync : Icons.http,
                ),
              ),
              const SizedBox(width: 8),
              IconButton(
                tooltip: 'Refresh cached snapshot',
                onPressed: widget.controller.busy ? null : () => widget.controller.refreshCompact(),
                icon: const Icon(Icons.refresh),
              ),
              PopupMenuButton<String>(
                onSelected: (value) {
                  if (value == 'logout') widget.controller.logout();
                },
                itemBuilder: (context) => [
                  PopupMenuItem<String>(
                    enabled: false,
                    child: Text('${widget.controller.session?.username ?? ''} (${widget.controller.session?.role ?? ''})'),
                  ),
                  const PopupMenuDivider(),
                  const PopupMenuItem<String>(value: 'logout', child: Text('Sign out')),
                ],
              ),
              const SizedBox(width: 6),
            ],
          ),
          body: wide
              ? Row(
                  children: [
                    NavigationRail(
                      selectedIndex: safeIndex,
                      onDestinationSelected: _selectDestination,
                      labelType: NavigationRailLabelType.all,
                      destinations: destinations
                          .map((item) => NavigationRailDestination(
                                icon: item.icon,
                                selectedIcon: item.selectedIcon,
                                label: Text(item.label),
                              ))
                          .toList(),
                    ),
                    const VerticalDivider(width: 1),
                    Expanded(child: body),
                  ],
                )
              : body,
          bottomNavigationBar: wide
              ? null
              : NavigationBar(
                  selectedIndex: safeIndex,
                  onDestinationSelected: _selectDestination,
                  destinations: destinations,
                ),
        );
      },
    );
  }
}
