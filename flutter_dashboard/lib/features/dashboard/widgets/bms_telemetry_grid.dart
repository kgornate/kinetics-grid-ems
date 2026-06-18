import 'package:flutter/material.dart';

import '../../../models/bms_telemetry.dart';
import '../../../widgets/telemetry_card.dart';
import 'dashboard_formatters.dart';

class BmsTelemetryGrid extends StatelessWidget {
  const BmsTelemetryGrid({super.key, this.telemetry});

  final BmsTelemetry? telemetry;

  @override
  Widget build(BuildContext context) {
    final b = telemetry;
    return LayoutBuilder(
      builder: (context, constraints) {
        var crossAxisCount = 3;
        if (constraints.maxWidth < 900) crossAxisCount = 2;
        if (constraints.maxWidth < 560) crossAxisCount = 1;

        return GridView.count(
          crossAxisCount: crossAxisCount,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          childAspectRatio: 2.35,
          crossAxisSpacing: 12,
          mainAxisSpacing: 12,
          children: [
            TelemetryCard(title: 'SOC', value: dashboardDoubleValue(b?.socPercent), unit: '%', icon: Icons.battery_full),
            TelemetryCard(title: 'SOH', value: dashboardDoubleValue(b?.sohPercent), unit: '%', icon: Icons.health_and_safety),
            TelemetryCard(title: 'Rack Voltage', value: dashboardDoubleValue(b?.rackVoltageV), unit: 'V', icon: Icons.bolt),
            TelemetryCard(title: 'Rack Current', value: dashboardDoubleValue(b?.rackCurrentA), unit: 'A', icon: Icons.electric_meter),
            TelemetryCard(title: 'Power', value: dashboardDoubleValue(b?.powerKw, digits: 2), unit: 'kW', icon: Icons.power),
            TelemetryCard(title: 'Max Cell Voltage', value: dashboardDoubleValue(b?.maxCellVoltageMv, digits: 0), unit: 'mV', icon: Icons.arrow_upward),
            TelemetryCard(title: 'Min Cell Voltage', value: dashboardDoubleValue(b?.minCellVoltageMv, digits: 0), unit: 'mV', icon: Icons.arrow_downward),
            TelemetryCard(title: 'Voltage Diff', value: dashboardDoubleValue(b?.cellVoltageDiffMv, digits: 0), unit: 'mV', icon: Icons.compare_arrows),
            TelemetryCard(title: 'Max Temp', value: dashboardDoubleValue(b?.maxCellTempC), unit: '°C', icon: Icons.device_thermostat),
            TelemetryCard(title: 'Min Temp', value: dashboardDoubleValue(b?.minCellTempC), unit: '°C', icon: Icons.thermostat),
            TelemetryCard(title: 'Insulation', value: dashboardDoubleValue(b?.insulationResistanceKohm, digits: 0), unit: 'kΩ', icon: Icons.security),
            TelemetryCard(title: 'Alarm Count', value: dashboardValue(b?.alarmCount), icon: Icons.warning_amber),
          ],
        );
      },
    );
  }
}
