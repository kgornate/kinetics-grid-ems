import 'package:flutter/material.dart';

import '../core/state/gateway_controller.dart';
import '../widgets/common_widgets.dart';
import 'alarms_screen.dart';
import 'control_sequence_screen.dart';
import 'diagnostics_screen.dart';
import 'historian_screen.dart';
import 'kalpa_monitoring_screen.dart';
import 'meter_screen.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key, required this.controller});

  final GatewayController controller;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  List<NavigationDestination> get _destinations => <NavigationDestination>[
    const NavigationDestination(
      icon: Icon(Icons.dashboard_outlined),
      selectedIcon: Icon(Icons.dashboard),
      label: 'Overview',
    ),
    const NavigationDestination(
      icon: Icon(Icons.battery_charging_full_outlined),
      selectedIcon: Icon(Icons.battery_charging_full),
      label: 'System BMS',
    ),
    const NavigationDestination(
      icon: Icon(Icons.view_column_outlined),
      selectedIcon: Icon(Icons.view_column),
      label: 'Racks',
    ),
    const NavigationDestination(
      icon: Icon(Icons.ac_unit_outlined),
      selectedIcon: Icon(Icons.ac_unit),
      label: 'Environment',
    ),
    const NavigationDestination(
      icon: Icon(Icons.power_outlined),
      selectedIcon: Icon(Icons.power),
      label: 'PCS',
    ),
    const NavigationDestination(
      icon: Icon(Icons.electric_meter_outlined),
      selectedIcon: Icon(Icons.electric_meter),
      label: 'Meter',
    ),
    if (widget.controller.isInternal)
      const NavigationDestination(
        icon: Icon(Icons.account_tree_outlined),
        selectedIcon: Icon(Icons.account_tree),
        label: 'Control',
      ),
    const NavigationDestination(
      icon: Icon(Icons.warning_amber_outlined),
      selectedIcon: Icon(Icons.warning_amber),
      label: 'Alarms',
    ),
    const NavigationDestination(
      icon: Icon(Icons.timeline_outlined),
      selectedIcon: Icon(Icons.timeline),
      label: 'Historian',
    ),
    const NavigationDestination(
      icon: Icon(Icons.monitor_heart_outlined),
      selectedIcon: Icon(Icons.monitor_heart),
      label: 'Diagnostics',
    ),
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
    return <Widget>[
      KalpaMonitoringScreen(controller: widget.controller, section: 'overview'),
      KalpaMonitoringScreen(controller: widget.controller, section: 'battery'),
      KalpaMonitoringScreen(controller: widget.controller, section: 'racks'),
      KalpaMonitoringScreen(
        controller: widget.controller,
        section: 'environment',
      ),
      KalpaMonitoringScreen(controller: widget.controller, section: 'pcs'),
      MeterScreen(controller: widget.controller, active: _index == 5),
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
            title: Text('Kalpa Gateway - ${destinations[safeIndex].label}'),
            actions: [
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 10),
                child: StatusPill(
                  label: widget.controller.wsConnected ? 'Live' : 'REST only',
                  good:
                      widget.controller.wsConnected ||
                      widget.controller.restConnected,
                  icon: widget.controller.wsConnected ? Icons.sync : Icons.http,
                ),
              ),
              const SizedBox(width: 8),
              IconButton(
                tooltip: 'Refresh cached snapshot',
                onPressed: widget.controller.busy
                    ? null
                    : () => widget.controller.refreshKalpa(),
                icon: const Icon(Icons.refresh),
              ),
              PopupMenuButton<String>(
                onSelected: (value) {
                  if (value == 'logout') widget.controller.logout();
                },
                itemBuilder: (context) => [
                  PopupMenuItem<String>(
                    enabled: false,
                    child: Text(
                      '${widget.controller.session?.username ?? ''} (${widget.controller.session?.role ?? ''})',
                    ),
                  ),
                  const PopupMenuDivider(),
                  const PopupMenuItem<String>(
                    value: 'logout',
                    child: Text('Sign out'),
                  ),
                ],
              ),
              const SizedBox(width: 6),
            ],
          ),
          body: wide
              ? Row(
                  children: [
                    SizedBox(
                      width: 178,
                      child: ListView(
                        children: [
                          const Padding(
                            padding: EdgeInsets.all(18),
                            child: Text(
                              'KALPA EMS',
                              style: TextStyle(fontWeight: FontWeight.bold),
                            ),
                          ),
                          ...List.generate(
                            destinations.length,
                            (index) => ListTile(
                              leading: safeIndex == index
                                  ? destinations[index].selectedIcon
                                  : destinations[index].icon,
                              title: Text(destinations[index].label),
                              selected: safeIndex == index,
                              onTap: () => _selectDestination(index),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const VerticalDivider(width: 1),
                    Expanded(child: body),
                  ],
                )
              : body,
          bottomNavigationBar: wide
              ? null
              : SafeArea(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 16,
                      vertical: 8,
                    ),
                    child: DropdownButton<int>(
                      isExpanded: true,
                      value: safeIndex,
                      items: List.generate(
                        destinations.length,
                        (i) => DropdownMenuItem(
                          value: i,
                          child: Text(destinations[i].label),
                        ),
                      ),
                      onChanged: (value) {
                        if (value != null) _selectDestination(value);
                      },
                    ),
                  ),
                ),
        );
      },
    );
  }
}
