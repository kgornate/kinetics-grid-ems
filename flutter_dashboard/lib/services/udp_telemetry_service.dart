import 'dart:async';
import 'dart:convert';
import 'dart:io';

import '../models/chiller_telemetry.dart';
import '../models/pcs_telemetry.dart';

class UdpTelemetryService {
  RawDatagramSocket? _socket;

  final StreamController<ChillerTelemetry> _telemetryController =
      StreamController<ChillerTelemetry>.broadcast();

  final StreamController<PcsTelemetry> _pcsTelemetryController =
      StreamController<PcsTelemetry>.broadcast();

  final StreamController<Map<String, dynamic>> _rawPacketController =
      StreamController<Map<String, dynamic>>.broadcast();

  Stream<ChillerTelemetry> get telemetryStream => _telemetryController.stream;
  Stream<PcsTelemetry> get pcsTelemetryStream => _pcsTelemetryController.stream;
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

        final chillerTelemetry = _parseChillerTelemetry(decoded);
        if (chillerTelemetry != null) {
          _telemetryController.add(chillerTelemetry);
        }

        final pcsTelemetry = _parsePcsTelemetry(decoded);
        if (pcsTelemetry != null) {
          _pcsTelemetryController.add(pcsTelemetry);
        }
      } catch (_) {
        // Ignore malformed UDP packets and keep listener alive.
      }
    });
  }

  ChillerTelemetry? _parseChillerTelemetry(Map<String, dynamic> packet) {
    final payload = _asMap(packet['payload']).isNotEmpty
        ? _asMap(packet['payload'])
        : packet;

    final data = _asMap(payload['data']);
    if (data.isEmpty) return null;

    // In PCS-only mode backend sends data: {"message": "PCS-only..."}.
    // Avoid treating that as chiller telemetry.
    final hasChillerKeys = data.containsKey('water_pump') ||
        data.containsKey('outlet_water_temp') ||
        data.containsKey('return_water_temp') ||
        data.containsKey('communication_status');

    if (!hasChillerKeys) return null;

    return ChillerTelemetry.fromJson(data);
  }

  PcsTelemetry? _parsePcsTelemetry(Map<String, dynamic> packet) {
    final payload = _asMap(packet['payload']).isNotEmpty
        ? _asMap(packet['payload'])
        : packet;

    Map<String, dynamic> pcs = _asMap(payload['pcs']);

    if (pcs.isEmpty) {
      final assets = _asMap(payload['assets']);
      pcs = _asMap(assets['pcs']);
    }

    if (pcs.isEmpty) return null;

    return PcsTelemetry.fromJson(pcs);
  }

  Map<String, dynamic> _asMap(dynamic value) {
    if (value is Map<String, dynamic>) return value;
    if (value is Map) return Map<String, dynamic>.from(value);
    return {};
  }

  Future<void> stop() async {
    _socket?.close();
    _socket = null;
  }

  Future<void> dispose() async {
    await stop();
    await _telemetryController.close();
    await _pcsTelemetryController.close();
    await _rawPacketController.close();
  }
}
