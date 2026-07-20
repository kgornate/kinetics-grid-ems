
import 'source_home_summary.dart';

class SiteDashboardSummary {
  const SiteDashboardSummary({
    required this.sourceCount,
    required this.onlineSourceCount,
    required this.assetCount,
    required this.onlineAssetCount,
    required this.totalSignalCount,
    required this.badSignalCount,
    required this.alarmCount,
    required this.storageEnabled,
    required this.gatewayMode,
    required this.commandsEnabled,
    required this.controlEnabled,
    required this.overallSoc,
    required this.siteActivePowerKw,
    required this.fireAlarmActive,
    required this.sources,
    required this.bessOnCount,
    required this.bessKnownCount,
  });

  final int sourceCount;
  final int onlineSourceCount;
  final int assetCount;
  final int onlineAssetCount;
  final int totalSignalCount;
  final int badSignalCount;
  final int alarmCount;
  final bool storageEnabled;
  final String gatewayMode;
  final bool commandsEnabled;
  final bool controlEnabled;
  final double? overallSoc;
  final double? siteActivePowerKw;
  final bool fireAlarmActive;
  final List<SourceHomeSummary> sources;
  final int bessOnCount;
  final int bessKnownCount;

  bool get gatewayHealthy =>
      sourceCount > 0 && onlineSourceCount == sourceCount && badSignalCount == 0;

  String get bessFleetLabel {
    if (bessKnownCount == 0) return '--';
    return '$bessOnCount/$bessKnownCount ON';
  }
}
