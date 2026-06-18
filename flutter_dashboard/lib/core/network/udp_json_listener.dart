import 'dart:async';
import 'dart:convert';
import 'dart:io';

/// Reusable UDP JSON listener for telemetry-style packets.
class UdpJsonListener {
  RawDatagramSocket? _socket;
  final StreamController<Map<String, dynamic>> _controller =
      StreamController<Map<String, dynamic>>.broadcast();

  Stream<Map<String, dynamic>> get stream => _controller.stream;
  bool get isRunning => _socket != null;

  Future<void> start({required int port}) async {
    if (_socket != null) return;
    _socket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, port);
    _socket!.listen((event) {
      if (event != RawSocketEvent.read) return;
      final datagram = _socket!.receive();
      if (datagram == null) return;
      try {
        final decoded = jsonDecode(utf8.decode(datagram.data));
        if (decoded is Map<String, dynamic>) {
          _controller.add(decoded);
        } else if (decoded is Map) {
          _controller.add(Map<String, dynamic>.from(decoded));
        }
      } catch (_) {
        // Ignore malformed UDP packets and keep the listener alive.
      }
    });
  }

  Future<void> stop() async {
    _socket?.close();
    _socket = null;
  }

  Future<void> dispose() async {
    await stop();
    await _controller.close();
  }
}
