import 'package:flutter/material.dart';

enum DashboardPage {
  home,
  topology,
  pcs,
  bms,
  chiller,
}

class DashboardNavActions extends StatelessWidget {
  const DashboardNavActions({
    super.key,
    required this.currentPage,
    required this.connectionLabel,
    required this.onHome,
    required this.onTopology,
    required this.onPcs,
    required this.onBms,
    required this.onChiller,
    required this.onLogout,
    this.refreshing = false,
  });

  final DashboardPage currentPage;
  final String connectionLabel;
  final VoidCallback onHome;
  final VoidCallback onTopology;
  final VoidCallback onPcs;
  final VoidCallback onBms;
  final VoidCallback onChiller;
  final VoidCallback onLogout;
  final bool refreshing;

  @override
  Widget build(BuildContext context) {
    Widget navButton(String label, DashboardPage page, VoidCallback onTap) {
      final selected = currentPage == page;
      if (selected) {
        return FilledButton.tonal(
          onPressed: null,
          child: Text(label),
        );
      }
      return TextButton(
        onPressed: onTap,
        child: Text(label),
      );
    }

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (refreshing)
          const Padding(
            padding: EdgeInsets.only(right: 8),
            child: SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
          ),
        navButton('Home', DashboardPage.home, onHome),
        const SizedBox(width: 4),
        navButton('Topology', DashboardPage.topology, onTopology),
        const SizedBox(width: 4),
        navButton('PCS', DashboardPage.pcs, onPcs),
        const SizedBox(width: 4),
        navButton('BMS', DashboardPage.bms, onBms),
        const SizedBox(width: 4),
        navButton('Chiller', DashboardPage.chiller, onChiller),
        const SizedBox(width: 10),
        Text(
          connectionLabel,
          style: const TextStyle(fontWeight: FontWeight.w600),
        ),
        const SizedBox(width: 6),
        IconButton(
          onPressed: onLogout,
          tooltip: 'Logout',
          icon: const Icon(Icons.logout),
        ),
      ],
    );
  }
}
