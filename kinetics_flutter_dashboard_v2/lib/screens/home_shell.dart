import 'package:flutter/material.dart';

import '../core/state/gateway_controller.dart';
import '../widgets/common_widgets.dart';
import 'alarms_screen.dart';
import 'bau_screen.dart';
import 'dashboard_screen.dart';
import 'diagnostics_screen.dart';
import 'environment_screen.dart';
import 'historian_screen.dart';
import 'racks_screen.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key, required this.controller});

  final GatewayController controller;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  static const _destinations = <NavigationDestination>[
    NavigationDestination(icon: Icon(Icons.dashboard_outlined), selectedIcon: Icon(Icons.dashboard), label: 'Overview'),
    NavigationDestination(icon: Icon(Icons.battery_charging_full_outlined), selectedIcon: Icon(Icons.battery_charging_full), label: 'BAU'),
    NavigationDestination(icon: Icon(Icons.view_column_outlined), selectedIcon: Icon(Icons.view_column), label: 'Racks'),
    NavigationDestination(icon: Icon(Icons.ac_unit_outlined), selectedIcon: Icon(Icons.ac_unit), label: 'Environment'),
    NavigationDestination(icon: Icon(Icons.warning_amber_outlined), selectedIcon: Icon(Icons.warning_amber), label: 'Alarms'),
    NavigationDestination(icon: Icon(Icons.timeline_outlined), selectedIcon: Icon(Icons.timeline), label: 'Historian'),
    NavigationDestination(icon: Icon(Icons.monitor_heart_outlined), selectedIcon: Icon(Icons.monitor_heart), label: 'Diagnostics'),
  ];

  List<Widget> get _screens {
    final bank = widget.controller.plant.bank;
    return <Widget>[
      DashboardScreen(controller: widget.controller),
      bank == null
          ? const Center(child: Text('No BAU/bank snapshot received yet.'))
          : BauScreen(controller: widget.controller),
      RacksScreen(controller: widget.controller),
      EnvironmentScreen(controller: widget.controller),
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
        final body = IndexedStack(index: _index, children: _screens);
        return Scaffold(
          appBar: AppBar(
            title: Text('Kinetics Gateway - ${_destinations[_index].label}'),
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
                      selectedIndex: _index,
                      onDestinationSelected: (value) => setState(() => _index = value),
                      labelType: NavigationRailLabelType.all,
                      destinations: _destinations
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
                  selectedIndex: _index,
                  onDestinationSelected: (value) => setState(() => _index = value),
                  destinations: _destinations,
                ),
        );
      },
    );
  }
}
