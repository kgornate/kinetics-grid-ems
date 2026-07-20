import 'pcs_fault_item.dart';

class BmsSourceSnapshot {
  const BmsSourceSnapshot({
    required this.sourceId,
    required this.displayName,
    required this.host,
    required this.port,
    required this.online,
    required this.systemStatusLabel,
    required this.chargeDischargeStatusLabel,
    required this.faultSummaryLabel,
    required this.alarmSummaryLabel,
    required this.faultItems,
    required this.alarmItems,
    required this.thresholdItems,
    this.socPercent,
    this.sohPercent,
    this.packVoltageV,
    this.packCurrentA,
    this.clusterResistanceMilliOhm,
    this.maxCellVoltageMv,
    this.minCellVoltageMv,
    this.maxCellVoltageId,
    this.minCellVoltageId,
    this.maxTempC,
    this.minTempC,
    this.maxTempId,
    this.minTempId,
    this.totalEnergyCharged,
    this.totalEnergyChargedUnit,
    this.totalEnergyDischarged,
    this.totalEnergyDischargedUnit,
  });

  final String sourceId;
  final String displayName;
  final String host;
  final int port;
  final bool online;

  final String systemStatusLabel;
  final String chargeDischargeStatusLabel;
  final String faultSummaryLabel;
  final String alarmSummaryLabel;
  final List<PcsFaultItem> faultItems;
  final List<PcsFaultItem> alarmItems;
  final List<PcsFaultItem> thresholdItems;

  final double? socPercent;
  final double? sohPercent;
  final double? packVoltageV;
  final double? packCurrentA;
  final double? clusterResistanceMilliOhm;
  final double? maxCellVoltageMv;
  final double? minCellVoltageMv;
  final int? maxCellVoltageId;
  final int? minCellVoltageId;
  final double? maxTempC;
  final double? minTempC;
  final int? maxTempId;
  final int? minTempId;
  final double? totalEnergyCharged;
  final String? totalEnergyChargedUnit;
  final double? totalEnergyDischarged;
  final String? totalEnergyDischargedUnit;

  List<PcsFaultItem> get activeFaultItems => faultItems.where((e) => e.active).toList();
  List<PcsFaultItem> get activeAlarmItems => alarmItems.where((e) => e.active).toList();

  bool get faultActive => activeFaultItems.isNotEmpty;
  bool get alarmActive => activeAlarmItems.isNotEmpty;
}
