import 'dart:async';
import 'dart:convert';
import 'dart:io';

/// Reusable line-oriented TCP JSON client.
class TcpSocketClient {
  final String host;
  final int port;
  final Duration timeout;

  const TcpSocketClient({
    required this.host,
    required this.port,
    required this.timeout,
  });

  Future<Map<String, dynamic>> sendJsonLine(Map<String, dynamic> packet) async {
    Socket? socket;
    try {
      socket = await Socket.connect(host, port, timeout: timeout);
      socket.write('${jsonEncode(packet)}\n');
      await socket.flush();

      final responseLine = await socket
          .cast<List<int>>()
          .transform(utf8.decoder)
          .transform(const LineSplitter())
          .first
          .timeout(timeout);

      final decoded = jsonDecode(responseLine);
      if (decoded is Map<String, dynamic>) return decoded;
      if (decoded is Map) return Map<String, dynamic>.from(decoded);
      throw const FormatException('TCP response is not a JSON object');
    } finally {
      socket?.destroy();
    }
  }
}
