import 'package:flutter/material.dart';

import '../../../models/chiller_telemetry.dart';
import '../../../widgets/telemetry_card.dart';
import 'dashboard_formatters.dart';

class ChillerTelemetryGrid extends StatelessWidget {
  const ChillerTelemetryGrid({super.key, this.telemetry});

  final ChillerTelemetry? telemetry;

  @override
  Widget build(BuildContext context) {
    final t = telemetry;
    return LayoutBuilder(
      builder: (context, constraints) {
        var crossAxisCount = 3;
        if (constraints.maxWidth < 800) crossAxisCount = 2;
        if (constraints.maxWidth < 520) crossAxisCount = 1;

        return GridView.count(
          crossAxisCount: crossAxisCount,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          childAspectRatio: 2.35,
          crossAxisSpacing: 12,
          mainAxisSpacing: 12,
          children: [
            TelemetryCard(title: 'Outlet Water Temp', value: dashboardDoubleValue(t?.outletWaterTemp), unit: '°C', icon: Icons.thermostat),
            TelemetryCard(title: 'Return Water Temp', value: dashboardDoubleValue(t?.returnWaterTemp), unit: '°C', icon: Icons.thermostat_auto),
            TelemetryCard(title: 'Ambient Temp', value: dashboardDoubleValue(t?.ambientTemp), unit: '°C', icon: Icons.device_thermostat),
            TelemetryCard(title: 'Outlet Pressure', value: dashboardDoubleValue(t?.outletWaterPressure, digits: 2), unit: 'Bar', icon: Icons.speed),
            TelemetryCard(title: 'Return Pressure', value: dashboardDoubleValue(t?.returnWaterPressure, digits: 2), unit: 'Bar', icon: Icons.speed_outlined),
            TelemetryCard(title: 'Set Temperature', value: dashboardValue(t?.setTemperature), unit: '°C', icon: Icons.tune),
            TelemetryCard(title: 'Control Mode', value: dashboardValue(t?.controlMode), icon: Icons.settings),
            TelemetryCard(title: 'Make-up Pump', value: dashboardValue(t?.makeupPump), icon: Icons.water_drop),
            TelemetryCard(title: 'Last Chiller Received', value: dashboardFormatTime(t?.receivedAt), icon: Icons.access_time),
          ],
        );
      },
    );
  }
}
