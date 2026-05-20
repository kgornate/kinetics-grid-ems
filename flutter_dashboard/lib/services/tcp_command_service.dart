import 'dart:convert';
import 'dart:io';
import 'dart:math';

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
  }) async {
    final requestId = _generateRequestId();

    final packet = <String, dynamic>{
      'type': 'command',
      'request_id': requestId,
      'timestamp': DateTime.now().toIso8601String(),
      'command': command.toUpperCase(),
      'verify': verify,
    };

    if (value != null) {
      packet['value'] = value;
    }

    Socket? socket;

    try {
      socket = await Socket.connect(
        gatewayIp,
        gatewayPort,
        timeout: timeout,
      );

      final message = '${jsonEncode(packet)}\n';
      socket.write(message);
      await socket.flush();

      final responseLine = await socket
          .cast<List<int>>()
          .transform(utf8.decoder)
          .transform(const LineSplitter())
          .first
          .timeout(timeout);

      final decoded = jsonDecode(responseLine);

      if (decoded is! Map<String, dynamic>) {
        throw Exception('Invalid response format');
      }

      return GatewayResponse.fromJson(Map<String, dynamic>.from(decoded));
    } catch (e) {
      return GatewayResponse(
        type: 'local_error',
        requestId: requestId,
        timestamp: DateTime.now().toIso8601String(),
        status: 'error',
        command: command.toUpperCase(),
        message: e.toString(),
        data: {},
      );
    } finally {
      socket?.destroy();
    }
  }

  String _generateRequestId() {
    final random = Random();
    final value = random.nextInt(0xFFFFFF).toRadixString(16).toUpperCase();
    return 'REQ_$value';
  }
}