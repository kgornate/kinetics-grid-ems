import 'dart:math';

import '../core/network/tcp_socket_client.dart';
import '../models/gateway_response.dart';

class TcpCommandService {
  final String gatewayIp;
  final int gatewayPort;
  final Duration timeout;

  TcpCommandService({
    required this.gatewayIp,
    required this.gatewayPort,
    required this.timeout,
  });

  Future<GatewayResponse> sendCommand({
    required String command,
    dynamic value,
    bool verify = true,
    String? requestId,
    Map<String, dynamic> params = const <String, dynamic>{},
  }) async {
    final effectiveRequestId = requestId ?? _generateRequestId();

    final packet = <String, dynamic>{
      'type': 'command',
      'request_id': effectiveRequestId,
      'timestamp': DateTime.now().toIso8601String(),
      'command': command.toUpperCase(),
      'verify': verify,
      ...params,
    };

    if (value != null) {
      packet['value'] = value;
    }

    try {
      final client = TcpSocketClient(
        host: gatewayIp,
        port: gatewayPort,
        timeout: timeout,
      );
      final decoded = await client.sendJsonLine(packet);
      return GatewayResponse.fromJson(decoded);
    } catch (e) {
      return GatewayResponse(
        type: 'local_error',
        requestId: effectiveRequestId,
        timestamp: DateTime.now().toIso8601String(),
        status: 'error',
        command: command.toUpperCase(),
        message: e.toString(),
        data: {},
      );
    }
  }

  String _generateRequestId() {
    final random = Random();
    final value = random.nextInt(0xFFFFFF).toRadixString(16).toUpperCase();
    return 'REQ_$value';
  }
}
