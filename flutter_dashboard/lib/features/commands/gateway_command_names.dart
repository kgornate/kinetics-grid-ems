/// Centralized gateway command names.
///
/// UI panels, repositories, and services should reference these constants
/// instead of scattering raw command strings throughout the app.
class GatewayCommandNames {
  const GatewayCommandNames._();

  // Gateway / aggregate commands.
  static const status = 'STATUS';
  static const readAllAssets = 'READ_ALL_ASSETS';
  static const readGatewayTelemetry = 'READ_GATEWAY_TELEMETRY';

  // Chiller commands.
  static const readChillerAll = 'READ_ALL';
  static const readChillerSettings = 'READ_SETTINGS';
  static const readChillerMode = 'READ_MODE';
  static const readChillerTemperature = 'READ_TEMP';
  static const readChillerOnOff = 'READ_ONOFF';
  static const setChillerTemperature = 'SET_TEMP';
  static const setChillerMode = 'SET_MODE';
  static const chillerOn = 'CHILLER_ON';
  static const chillerOff = 'CHILLER_OFF';

  // PCS / inverter commands.
  static const readPcs = 'PCS_READ';
  static const readPcsAlias = 'READ_PCS';
  static const pcsStatus = 'PCS_STATUS';
  static const setPcsActivePower = 'PCS_SET_ACTIVE_POWER';
  static const setPcsReactivePower = 'PCS_SET_REACTIVE_POWER';
  static const pcsHeartbeat = 'PCS_HEARTBEAT';
  static const pcsPowerOn = 'PCS_POWER_ON';
  static const pcsPowerOff = 'PCS_POWER_OFF';
  static const pcsResetFault = 'PCS_RESET_FAULT';

  // BMS / BCU commands.
  static const readBms = 'READ_BMS';
  static const readBmsAll = 'READ_BMS_ALL';
  static const readBmsAllAlias = 'BMS_READ_ALL';
  static const readBmsAlarms = 'READ_BMS_ALARMS';
  static const readBmsAlarmsAlias = 'BMS_READ_ALARMS';
  static const bmsFanAuto = 'BMS_FAN_AUTO';
  static const bmsFanOn = 'BMS_FAN_ON';
  static const bmsFanOff = 'BMS_FAN_OFF';

  static const startBmsPrecharge = 'START_BMS_PRECHARGE';
  static const stopBmsPrecharge = 'STOP_BMS_PRECHARGE';
  static const startBmsInsulationTest = 'START_BMS_INSULATION_TEST';
  static const startInsulationTest = 'START_INSULATION_TEST';
  static const resetBcu = 'RESET_BCU';
  static const resetBms = 'RESET_BMS';

  static String normalize(String command) => command.trim().toUpperCase();

  static bool isBmsReadCommand(String command) {
    final normalized = normalize(command);
    return normalized == readBms ||
        normalized == readBmsAll ||
        normalized == readBmsAllAlias ||
        normalized == readBmsAlarms ||
        normalized == readBmsAlarmsAlias;
  }

  static bool isPcsReadCommand(String command) {
    final normalized = normalize(command);
    return normalized == readPcs ||
        normalized == readPcsAlias ||
        normalized == pcsStatus;
  }

  static bool isGatewayReadCommand(String command) {
    final normalized = normalize(command);
    return normalized == readAllAssets || normalized == readGatewayTelemetry;
  }

  static bool isChillerReadCommand(String command) {
    final normalized = normalize(command);
    return normalized == readChillerAll ||
        normalized == readChillerSettings ||
        normalized == readChillerMode ||
        normalized == readChillerTemperature ||
        normalized == readChillerOnOff;
  }

  static bool isBmsCommand(String command) {
    final normalized = normalize(command);
    return normalized.startsWith('BMS_') ||
        isBmsReadCommand(normalized) ||
        normalized == startBmsPrecharge ||
        normalized == stopBmsPrecharge ||
        normalized == startBmsInsulationTest ||
        normalized == startInsulationTest ||
        normalized == resetBcu ||
        normalized == resetBms;
  }

  static bool isPcsCommand(String command) => normalize(command).startsWith('PCS_') || isPcsReadCommand(command);

  static bool isChillerCommand(String command) {
    final normalized = normalize(command);
    return isChillerReadCommand(normalized) ||
        normalized == setChillerTemperature ||
        normalized == setChillerMode ||
        normalized == chillerOn ||
        normalized == chillerOff;
  }
}
