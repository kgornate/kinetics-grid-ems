import 'pcs_fault_item.dart';

class FireSourceSnapshot {
  const FireSourceSnapshot({
    required this.sourceId,
    required this.displayName,
    required this.host,
    required this.port,
    required this.online,
    required this.communicationStatusLabel,
    required this.faultSummaryLabel,
    required this.alarmSummaryLabel,
    required this.faultItems,
    required this.alarmItems,
    required this.configItems,
    this.temperatureC,
    this.co1,
    this.co2,
    this.co3,
    this.activationStatusLabel,
    this.feedbackStatusLabel,
    this.infraredHighLevel,
    this.infraredLowLevel,
    this.fanDamperAlarmLabel,
    this.fanDamperStatusLabel,
    this.audibleVisualAlarmLabel,
    this.audibleVisualStatusLabel,
  });

  final String sourceId;
  final String displayName;
  final String host;
  final int port;
  final bool online;

  final String communicationStatusLabel;
  final String faultSummaryLabel;
  final String alarmSummaryLabel;
  final List<PcsFaultItem> faultItems;
  final List<PcsFaultItem> alarmItems;
  final List<PcsFaultItem> configItems;

  final double? temperatureC;
  final double? co1;
  final double? co2;
  final double? co3;
  final String? activationStatusLabel;
  final String? feedbackStatusLabel;
  final double? infraredHighLevel;
  final double? infraredLowLevel;
  final String? fanDamperAlarmLabel;
  final String? fanDamperStatusLabel;
  final String? audibleVisualAlarmLabel;
  final String? audibleVisualStatusLabel;

  List<PcsFaultItem> get activeFaultItems => faultItems.where((e) => e.active).toList();
  List<PcsFaultItem> get activeAlarmItems => alarmItems.where((e) => e.active).toList();
}
