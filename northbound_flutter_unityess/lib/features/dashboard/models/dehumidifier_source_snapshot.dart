import 'pcs_fault_item.dart';

class DehumidifierSourceSnapshot {
  const DehumidifierSourceSnapshot({
    required this.sourceId,
    required this.displayName,
    required this.host,
    required this.port,
    required this.online,
    required this.onlinePointLabel,
    required this.operatingModeLabel,
    required this.temperatureControlStatusLabel,
    required this.dehumidificationStatusLabel,
    required this.alarmStatusLabel,
    required this.humidityControlModeLabel,
    required this.dehumidificationSwitchLabel,
    required this.faultSummaryLabel,
    required this.alarmSummaryLabel,
    required this.faultItems,
    required this.alarmItems,
    required this.configItems,
    this.currentTemperatureC,
    this.currentHumidityPct,
    this.controllerInternalTemperatureC,
    this.temperatureSettingC,
    this.temperatureHysteresisC,
    this.humiditySettingPct,
    this.humidityHysteresisPct,
    this.communicationBaudRate,
  });

  final String sourceId;
  final String displayName;
  final String host;
  final int port;
  final bool online;

  final String onlinePointLabel;
  final String operatingModeLabel;
  final String temperatureControlStatusLabel;
  final String dehumidificationStatusLabel;
  final String alarmStatusLabel;
  final String humidityControlModeLabel;
  final String dehumidificationSwitchLabel;
  final String faultSummaryLabel;
  final String alarmSummaryLabel;
  final List<PcsFaultItem> faultItems;
  final List<PcsFaultItem> alarmItems;
  final List<PcsFaultItem> configItems;

  final double? currentTemperatureC;
  final double? currentHumidityPct;
  final double? controllerInternalTemperatureC;
  final double? temperatureSettingC;
  final double? temperatureHysteresisC;
  final double? humiditySettingPct;
  final double? humidityHysteresisPct;
  final double? communicationBaudRate;

  List<PcsFaultItem> get activeFaultItems => faultItems.where((e) => e.active).toList();
  List<PcsFaultItem> get activeAlarmItems => alarmItems.where((e) => e.active).toList();
}
