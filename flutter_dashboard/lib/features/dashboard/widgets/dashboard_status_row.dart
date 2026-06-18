import 'package:flutter/material.dart';

import '../../../models/bms_telemetry.dart';
import '../../../models/chiller_telemetry.dart';
import '../../../models/pcs_telemetry.dart';
import '../../../widgets/status_indicator.dart';

class DashboardStatusRow extends StatelessWidget {
  const DashboardStatusRow({
    super.key,
    required this.udpRunning,
    this.chiller,
    this.pcs,
    this.bms,
  });

  final bool udpRunning;
  final ChillerTelemetry? chiller;
  final PcsTelemetry? pcs;
  final BmsTelemetry? bms;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: [
        StatusIndicator(
          label: 'Gateway UDP',
          status: udpRunning ? 'LISTENING' : 'STOPPED',
          active: udpRunning,
        ),
        StatusIndicator(
          label: 'BMS Comm',
          status: bms?.effectiveCommStatus,
          active: bms?.isOnline ?? false,
        ),
        StatusIndicator(
          label: 'BMS State',
          status: bms?.bcuState,
          active: bms != null &&
              (bms!.bcuState == null ||
                  bms!.bcuState!.toLowerCase().contains('normal')),
        ),
        StatusIndicator(
          label: 'BMS Alarms',
          status: bms == null ? '--' : '${bms!.alarmCount}',
          active: bms != null && !bms!.hasAlarms,
        ),
        StatusIndicator(
          label: 'PCS Comm',
          status: pcs?.commStatus,
          active: pcs?.isOnline ?? false,
        ),
        StatusIndicator(
          label: 'PCS Status',
          status: pcs?.operatingStatus,
          active: pcs?.isRunning ?? false,
        ),
        StatusIndicator(
          label: 'PCS Fault',
          status: pcs == null ? '--' : (pcs!.faultStatus ? 'FAULT' : 'NORMAL'),
          active: pcs != null && !pcs!.faultStatus,
        ),
        StatusIndicator(
          label: 'Chiller Comm',
          status: chiller?.communicationStatus,
          active: chiller?.isOnline ?? false,
        ),
        StatusIndicator(
          label: 'Water Pump',
          status: chiller?.waterPump,
          active: chiller?.waterPump == 'RUNNING',
        ),
      ],
    );
  }
}
