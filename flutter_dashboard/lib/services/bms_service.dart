import '../config/app_config.dart';
import '../models/bms_telemetry.dart';
import '../models/gateway_response.dart';
import 'tcp_command_service.dart';

class BmsService {
  final TcpCommandService tcp;

  BmsService({required this.tcp});

  factory BmsService.forGateway(String gatewayIp) {
    return BmsService(
      tcp: TcpCommandService(
        gatewayIp: gatewayIp,
        gatewayPort: AppConfig.tcpCommandPort,
        timeout: AppConfig.tcpTimeout,
      ),
    );
  }

  Future<BmsCommandResult> readAll() async {
    return _sendAndMaybeParse('READ_BMS_ALL');
  }

  Future<BmsCommandResult> readAlarms() async {
    return _sendAndMaybeParse('READ_BMS_ALARMS');
  }

  Future<BmsCommandResult> startPrecharge() async {
    return _sendAndMaybeParse('START_BMS_PRECHARGE');
  }

  Future<BmsCommandResult> stopPrecharge() async {
    return _sendAndMaybeParse('STOP_BMS_PRECHARGE');
  }

  Future<BmsCommandResult> startInsulationTest() async {
    return _sendAndMaybeParse('START_BMS_INSULATION_TEST');
  }

  Future<BmsCommandResult> fanAuto() async {
    return _sendAndMaybeParse('BMS_FAN_AUTO');
  }

  Future<BmsCommandResult> fanOn() async {
    return _sendAndMaybeParse('BMS_FAN_ON');
  }

  Future<BmsCommandResult> fanOff() async {
    return _sendAndMaybeParse('BMS_FAN_OFF');
  }

  Future<BmsCommandResult> resetBcu() async {
    return _sendAndMaybeParse('RESET_BCU');
  }

  Future<BmsCommandResult> _sendAndMaybeParse(String command) async {
    final response = await tcp.sendCommand(command: command, verify: true);
    BmsTelemetry? telemetry;

    if (response.isOk && response.data.isNotEmpty) {
      try {
        telemetry = BmsTelemetry.fromJson(response.data);
      } catch (_) {
        telemetry = null;
      }
    }

    return BmsCommandResult(response: response, telemetry: telemetry);
  }
}

class BmsCommandResult {
  final GatewayResponse response;
  final BmsTelemetry? telemetry;

  BmsCommandResult({required this.response, required this.telemetry});
}
