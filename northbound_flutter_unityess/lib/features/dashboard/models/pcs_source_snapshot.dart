import 'pcs_fault_item.dart';

class PcsSourceSnapshot {
  const PcsSourceSnapshot({
    required this.sourceId,
    required this.displayName,
    required this.host,
    required this.port,
    required this.online,
    required this.runningStatusLabel,
    required this.operatingModeLabel,
    required this.gridModeLabel,
    required this.chargeDischargeLabel,
    required this.faultSummaryLabel,
    required this.alarmSummaryLabel,
    required this.faultItems,
    required this.alarmItems,
    this.activePowerKw,
    this.dcPowerKw,
    this.gridFrequencyHz,
    this.acVoltageV,
    this.acCurrentA,
    this.dcVoltageV,
  });

  final String sourceId;
  final String displayName;
  final String host;
  final int port;
  final bool online;

  final String runningStatusLabel;
  final String operatingModeLabel;
  final String gridModeLabel;
  final String chargeDischargeLabel;
  final String faultSummaryLabel;
  final String alarmSummaryLabel;

  final List<PcsFaultItem> faultItems;
  final List<PcsFaultItem> alarmItems;

  final double? activePowerKw;
  final double? dcPowerKw;
  final double? gridFrequencyHz;
  final double? acVoltageV;
  final double? acCurrentA;
  final double? dcVoltageV;

  List<PcsFaultItem> get activeFaultItems => faultItems.where((e) => e.active).toList();
  List<PcsFaultItem> get activeAlarmItems => alarmItems.where((e) => e.active).toList();

  bool get faultActive => activeFaultItems.isNotEmpty;
  bool get alarmActive => activeAlarmItems.isNotEmpty;
}
