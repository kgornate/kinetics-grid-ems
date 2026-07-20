
class SourceHomeSummary {
  const SourceHomeSummary({
    required this.sourceId,
    required this.displayName,
    required this.host,
    required this.port,
    required this.online,
    required this.assetCount,
    required this.onlineAssetCount,
    required this.signalCount,
    required this.badSignalCount,
    this.soc,
    this.activePowerKw,
    required this.fireAlarmActive,
    required this.pcsOnline,
    required this.bmsOnline,
    required this.liquidCoolingOnline,
    required this.fireOnline,
    required this.dehumidifierOnline,
    required this.bessOn,
    required this.bessStatusLabel,
    required this.bessModeLabel,
    required this.controlAuthorityLabel,
  });

  final String sourceId;
  final String displayName;
  final String host;
  final int port;
  final bool online;
  final int assetCount;
  final int onlineAssetCount;
  final int signalCount;
  final int badSignalCount;
  final double? soc;
  final double? activePowerKw;
  final bool fireAlarmActive;
  final bool pcsOnline;
  final bool bmsOnline;
  final bool liquidCoolingOnline;
  final bool fireOnline;
  final bool dehumidifierOnline;
  final bool? bessOn;
  final String bessStatusLabel;
  final String bessModeLabel;
  final String controlAuthorityLabel;

  String get shortTitle => displayName.isNotEmpty ? displayName : sourceId;

  bool get healthy => online && badSignalCount == 0;
}
