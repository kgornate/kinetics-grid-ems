
import 'pcs_fault_item.dart';

class UtilityMeterSourceSnapshot {
  const UtilityMeterSourceSnapshot({
    required this.sourceId,
    required this.displayName,
    required this.host,
    required this.port,
    required this.online,
    required this.statusLabel,
    required this.operatingModeLabel,
    required this.faultSummaryLabel,
    required this.alarmSummaryLabel,
    required this.faultItems,
    required this.alarmItems,
    required this.configItems,
    this.frequencyHz,
    this.activePowerKw,
    this.reactivePowerKvar,
    this.powerFactor,
    this.lineVoltageV,
    this.lineCurrentA,
    this.importEnergyKwh,
    this.exportEnergyKwh,
  });

  final String sourceId;
  final String displayName;
  final String host;
  final int port;
  final bool online;

  final String statusLabel;
  final String operatingModeLabel;
  final String faultSummaryLabel;
  final String alarmSummaryLabel;
  final List<PcsFaultItem> faultItems;
  final List<PcsFaultItem> alarmItems;
  final List<PcsFaultItem> configItems;

  final double? frequencyHz;
  final double? activePowerKw;
  final double? reactivePowerKvar;
  final double? powerFactor;
  final double? lineVoltageV;
  final double? lineCurrentA;
  final double? importEnergyKwh;
  final double? exportEnergyKwh;

  List<PcsFaultItem> get activeFaultItems => faultItems.where((e) => e.active).toList();
  List<PcsFaultItem> get activeAlarmItems => alarmItems.where((e) => e.active).toList();
}
