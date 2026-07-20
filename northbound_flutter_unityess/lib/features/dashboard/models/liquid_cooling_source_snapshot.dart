import 'pcs_fault_item.dart';

class LiquidCoolingSourceSnapshot {
  const LiquidCoolingSourceSnapshot({
    required this.sourceId,
    required this.displayName,
    required this.host,
    required this.port,
    required this.online,
    required this.powerStatusLabel,
    required this.operatingModeLabel,
    required this.alarmSummaryLabel,
    required this.faultSummaryLabel,
    required this.faultItems,
    required this.alarmItems,
    this.coolingSetTempC,
    this.heatingSetTempC,
    this.inletWaterTempC,
    this.outletWaterTempC,
    this.inletWaterPressureBar,
    this.outletWaterPressureBar,
    this.outletHighTempAlarmValueC,
    this.outletLowTempAlarmValueC,
    this.outletHighPressureAlarmValueBar,
    this.inletLowPressureAlarmValueBar,
  });

  final String sourceId;
  final String displayName;
  final String host;
  final int port;
  final bool online;

  final String powerStatusLabel;
  final String operatingModeLabel;
  final String alarmSummaryLabel;
  final String faultSummaryLabel;
  final List<PcsFaultItem> faultItems;
  final List<PcsFaultItem> alarmItems;

  final double? coolingSetTempC;
  final double? heatingSetTempC;
  final double? inletWaterTempC;
  final double? outletWaterTempC;
  final double? inletWaterPressureBar;
  final double? outletWaterPressureBar;
  final double? outletHighTempAlarmValueC;
  final double? outletLowTempAlarmValueC;
  final double? outletHighPressureAlarmValueBar;
  final double? inletLowPressureAlarmValueBar;

  List<PcsFaultItem> get activeFaultItems => faultItems.where((e) => e.active).toList();
  List<PcsFaultItem> get activeAlarmItems => alarmItems.where((e) => e.active).toList();
}
