
import 'pcs_fault_item.dart';

class EmsSystemSourceSnapshot {
  const EmsSystemSourceSnapshot({
    required this.sourceId,
    required this.displayName,
    required this.host,
    required this.port,
    required this.online,
    required this.systemStatusLabel,
    required this.manualAutoModeLabel,
    required this.manualModeControlLabel,
    required this.autoModeControlLabel,
    required this.chargeDischargeControlModeLabel,
    required this.powerCommandLabel,
    required this.pcsPowerControlLabel,
    required this.bmsPowerControlLabel,
    required this.faultSummaryLabel,
    required this.alarmSummaryLabel,
    required this.faultItems,
    required this.alarmItems,
    required this.configItems,
    this.chargeCutoffSocPct,
    this.dischargeCutoffSocPct,
    this.chargeLimitKw,
    this.dischargeLimitKw,
    this.actualActivePowerKw,
    this.batterySocPct,
  });

  final String sourceId;
  final String displayName;
  final String host;
  final int port;
  final bool online;

  final String systemStatusLabel;
  final String manualAutoModeLabel;
  final String manualModeControlLabel;
  final String autoModeControlLabel;
  final String chargeDischargeControlModeLabel;
  final String powerCommandLabel;
  final String pcsPowerControlLabel;
  final String bmsPowerControlLabel;
  final String faultSummaryLabel;
  final String alarmSummaryLabel;
  final List<PcsFaultItem> faultItems;
  final List<PcsFaultItem> alarmItems;
  final List<PcsFaultItem> configItems;

  final double? chargeCutoffSocPct;
  final double? dischargeCutoffSocPct;
  final double? chargeLimitKw;
  final double? dischargeLimitKw;
  final double? actualActivePowerKw;
  final double? batterySocPct;

  List<PcsFaultItem> get activeFaultItems => faultItems.where((e) => e.active).toList();
  List<PcsFaultItem> get activeAlarmItems => alarmItems.where((e) => e.active).toList();
}
