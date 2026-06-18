import 'package:flutter/material.dart';

import '../../../models/pcs_telemetry.dart';
import '../../../widgets/telemetry_card.dart';
import 'dashboard_formatters.dart';

class PcsTelemetryGrid extends StatelessWidget {
  const PcsTelemetryGrid({super.key, this.telemetry});

  final PcsTelemetry? telemetry;

  @override
  Widget build(BuildContext context) {
    final p = telemetry;
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
            TelemetryCard(title: 'Active Power', value: dashboardDoubleValue(p?.activePowerKw), unit: 'kW', icon: Icons.bolt),
            TelemetryCard(title: 'Reactive Power', value: dashboardDoubleValue(p?.reactivePowerKvar), unit: 'kvar', icon: Icons.electrical_services),
            TelemetryCard(title: 'Power Factor', value: dashboardDoubleValue(p?.powerFactor, digits: 2), icon: Icons.speed),
            TelemetryCard(title: 'Frequency', value: dashboardDoubleValue(p?.frequencyHz, digits: 2), unit: 'Hz', icon: Icons.show_chart),
            TelemetryCard(title: 'Battery Voltage', value: dashboardDoubleValue(p?.batteryVoltageV), unit: 'V', icon: Icons.battery_charging_full),
            TelemetryCard(title: 'Battery Current', value: dashboardDoubleValue(p?.batteryCurrentA), unit: 'A', icon: Icons.electric_meter),
            TelemetryCard(title: 'DC Power', value: dashboardDoubleValue(p?.dcPowerKw), unit: 'kW', icon: Icons.power),
            TelemetryCard(title: 'Bus Voltage', value: dashboardDoubleValue(p?.busVoltageV), unit: 'V', icon: Icons.cable),
            TelemetryCard(title: 'AB Line Voltage', value: dashboardDoubleValue(p?.abVoltageV), unit: 'V', icon: Icons.offline_bolt),
            TelemetryCard(title: 'BC Line Voltage', value: dashboardDoubleValue(p?.bcVoltageV), unit: 'V', icon: Icons.offline_bolt),
            TelemetryCard(title: 'CA Line Voltage', value: dashboardDoubleValue(p?.caVoltageV), unit: 'V', icon: Icons.offline_bolt),
            TelemetryCard(title: 'Phase A Current', value: dashboardDoubleValue(p?.phaseACurrentA), unit: 'A', icon: Icons.electrical_services),
            TelemetryCard(title: 'IGBT Temp', value: dashboardDoubleValue(p?.igbtTemperatureC), unit: '°C', icon: Icons.device_thermostat),
            TelemetryCard(title: 'Ambient Temp', value: dashboardDoubleValue(p?.ambientTemperatureC), unit: '°C', icon: Icons.thermostat),
            TelemetryCard(title: 'Last PCS Update', value: dashboardFormatTime(p?.receivedAt), icon: Icons.access_time),
          ],
        );
      },
    );
  }
}
