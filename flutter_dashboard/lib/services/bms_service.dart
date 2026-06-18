import '../config/app_config.dart';
import '../models/bms_telemetry.dart';
import '../models/gateway_response.dart';
import 'tcp_command_service.dart';
import '../features/commands/commands.dart';

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
    return _sendAndMaybeParse(GatewayCommandNames.readBmsAll);
  }

  Future<BmsCommandResult> readAlarms() async {
    return _sendAndMaybeParse(GatewayCommandNames.readBmsAlarms);
  }

  Future<BmsCommandResult> startPrecharge() async {
    return _sendAndMaybeParse(GatewayCommandNames.startBmsPrecharge);
  }

  Future<BmsCommandResult> stopPrecharge() async {
    return _sendAndMaybeParse(GatewayCommandNames.stopBmsPrecharge);
  }

  Future<BmsCommandResult> startInsulationTest() async {
    return _sendAndMaybeParse(GatewayCommandNames.startBmsInsulationTest);
  }

  Future<BmsCommandResult> fanAuto() async {
    return _sendAndMaybeParse(GatewayCommandNames.bmsFanAuto);
  }

  Future<BmsCommandResult> fanOn() async {
    return _sendAndMaybeParse(GatewayCommandNames.bmsFanOn);
  }

  Future<BmsCommandResult> fanOff() async {
    return _sendAndMaybeParse(GatewayCommandNames.bmsFanOff);
  }

  Future<BmsCommandResult> resetBcu() async {
    return _sendAndMaybeParse(GatewayCommandNames.resetBcu);
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
