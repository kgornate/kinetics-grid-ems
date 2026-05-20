import 'dart:async';
import 'dart:convert';
import 'dart:io';

import '../models/chiller_telemetry.dart';

class UdpTelemetryService {
  RawDatagramSocket? _socket;

  final StreamController<ChillerTelemetry> _telemetryController =
      StreamController<ChillerTelemetry>.broadcast();

  final StreamController<Map<String, dynamic>> _rawPacketController =
      StreamController<Map<String, dynamic>>.broadcast();

  Stream<ChillerTelemetry> get telemetryStream => _telemetryController.stream;
  Stream<Map<String, dynamic>> get rawPacketStream => _rawPacketController.stream;

  bool get isRunning => _socket != null;

  Future<void> start({required int port}) async {
    if (_socket != null) return;

    _socket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, port);

    _socket!.listen((RawSocketEvent event) {
      if (event != RawSocketEvent.read) return;

      final datagram = _socket!.receive();
      if (datagram == null) return;

      try {
        final message = utf8.decode(datagram.data);
        final decoded = jsonDecode(message);

        if (decoded is! Map<String, dynamic>) return;

        _rawPacketController.add(decoded);

        final telemetry = _parseTelemetry(decoded);
        if (telemetry != null) {
          _telemetryController.add(telemetry);
        }
      } catch (_) {
        // Ignore malformed UDP packets and keep listener alive.
      }
    });
  }

  ChillerTelemetry? _parseTelemetry(Map<String, dynamic> packet) {
    final payload = packet['payload'] is Map<String, dynamic>
        ? Map<String, dynamic>.from(packet['payload'])
        : packet;

    final data = payload['data'];

    if (data is! Map<String, dynamic>) return null;

    return ChillerTelemetry.fromJson(Map<String, dynamic>.from(data));
  }

  Future<void> stop() async {
    _socket?.close();
    _socket = null;
  }

  Future<void> dispose() async {
    await stop();
    await _telemetryController.close();
    await _rawPacketController.close();
  }
}