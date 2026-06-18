import '../config/app_config.dart';
import '../models/models.dart';
import '../services/bms_service.dart';
import '../services/tcp_command_service.dart';
import 'repository_exception.dart';
import '../features/commands/commands.dart';

/// Repository for TCP command execution.
///
/// Existing TCP command behavior is preserved. This repository gives future
/// screens/controllers a typed and centralized command boundary.
class CommandRepository {
  final TcpCommandService tcp;
  final BmsService bms;

  CommandRepository({
    required this.tcp,
    BmsService? bms,
  }) : bms = bms ?? BmsService(tcp: tcp);

  factory CommandRepository.forGateway(String gatewayIp) {
    final tcp = TcpCommandService(
      gatewayIp: gatewayIp,
      gatewayPort: AppConfig.tcpCommandPort,
      timeout: AppConfig.tcpTimeout,
    );
    return CommandRepository(tcp: tcp);
  }

  Future<GatewayCommandResponse> sendRawCommand(
    String command, {
    dynamic value,
    bool verify = true,
    String? requestId,
    Map<String, dynamic> params = const <String, dynamic>{},
  }) async {
    try {
      final response = await tcp.sendCommand(
        command: command,
        value: value,
        verify: verify,
        requestId: requestId,
        params: params,
      );
      return GatewayCommandResponse.fromJson(<String, dynamic>{
        'status': response.status,
        'command': response.command,
        'request_id': response.requestId,
        'message': response.message,
        'data': response.data,
      });
    } catch (error) {
      throw RepositoryException('Failed to send command $command', cause: error);
    }
  }


  Future<GatewayCommandResponse> sendDefinition(
    CommandDefinition definition, {
    dynamic value,
    bool verify = true,
    String? requestId,
    Map<String, dynamic> params = const <String, dynamic>{},
  }) {
    return sendRawCommand(
      definition.command,
      value: value,
      verify: verify,
      requestId: requestId,
      params: params,
    );
  }

  Future<GatewayCommandResponse> sendCommandRequest(
    GatewayCommandRequest request, {
    bool verify = true,
  }) {
    return sendRawCommand(
      request.command,
      value: request.value,
      verify: verify,
      requestId: request.requestId,
      params: request.params,
    );
  }

  Future<GatewayCommandResponse> readAllAssets() {
    return sendRawCommand(GatewayCommandNames.readAllAssets);
  }

  Future<GatewayCommandResponse> readStatus() {
    return sendRawCommand(GatewayCommandNames.status);
  }

  Future<GatewayCommandResponse> readPcs() {
    return sendRawCommand(GatewayCommandNames.readPcs);
  }

  Future<GatewayCommandResponse> setPcsActivePower(double powerKw) {
    return sendRawCommand(GatewayCommandNames.setPcsActivePower, value: powerKw);
  }

  Future<BmsCommandResult> readBmsAll() async {
    try {
      return await bms.readAll();
    } catch (error) {
      throw RepositoryException('Failed to read BMS telemetry', cause: error);
    }
  }

  Future<BmsCommandResult> readBmsAlarms() async {
    try {
      return await bms.readAlarms();
    } catch (error) {
      throw RepositoryException('Failed to read BMS alarms', cause: error);
    }
  }
}
