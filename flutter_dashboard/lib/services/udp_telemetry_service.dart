import 'dart:async';
import '../core/network/udp_json_listener.dart';
import '../core/utils/json_utils.dart';
import '../models/bms_telemetry.dart';
import '../models/chiller_telemetry.dart';
import '../models/pcs_telemetry.dart';

class UdpTelemetryService {
  final UdpJsonListener _listener = UdpJsonListener();
  StreamSubscription<Map<String, dynamic>>? _listenerSubscription;

  final StreamController<ChillerTelemetry> _telemetryController =
      StreamController<ChillerTelemetry>.broadcast();

  final StreamController<PcsTelemetry> _pcsTelemetryController =
      StreamController<PcsTelemetry>.broadcast();

  final StreamController<BmsTelemetry> _bmsTelemetryController =
      StreamController<BmsTelemetry>.broadcast();

  final StreamController<Map<String, dynamic>> _rawPacketController =
      StreamController<Map<String, dynamic>>.broadcast();

  Stream<ChillerTelemetry> get telemetryStream => _telemetryController.stream;
  Stream<PcsTelemetry> get pcsTelemetryStream => _pcsTelemetryController.stream;
  Stream<BmsTelemetry> get bmsTelemetryStream => _bmsTelemetryController.stream;
  Stream<Map<String, dynamic>> get rawPacketStream => _rawPacketController.stream;

  bool get isRunning => _listener.isRunning;

  Future<void> start({required int port}) async {
    if (_listener.isRunning) return;

    _listenerSubscription ??= _listener.stream.listen((decoded) {
      _rawPacketController.add(decoded);

      final chillerTelemetry = _parseChillerTelemetry(decoded);
      if (chillerTelemetry != null) {
        _telemetryController.add(chillerTelemetry);
      }

      final pcsTelemetry = _parsePcsTelemetry(decoded);
      if (pcsTelemetry != null) {
        _pcsTelemetryController.add(pcsTelemetry);
      }

      final bmsTelemetry = _parseBmsTelemetry(decoded);
      if (bmsTelemetry != null) {
        _bmsTelemetryController.add(bmsTelemetry);
      }
    });

    await _listener.start(port: port);
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


  BmsTelemetry? _parseBmsTelemetry(Map<String, dynamic> packet) {
    final payload = _asMap(packet['payload']).isNotEmpty
        ? _asMap(packet['payload'])
        : packet;

    Map<String, dynamic> bms = _asMap(payload['bms']);

    if (bms.isEmpty) {
      final assets = _asMap(payload['assets']);
      bms = _asMap(assets['bms']);
    }

    if (bms.isEmpty) {
      final data = _asMap(payload['data']);
      final hasBmsKeys = data.containsKey('soc_percent') ||
          data.containsKey('rack_voltage_v') ||
          data.containsKey('max_cell_voltage_mv') ||
          data['asset_id']?.toString() == 'bms_1';
      if (hasBmsKeys) bms = data;
    }

    if (bms.isEmpty) return null;

    return BmsTelemetry.fromJson(bms);
  }

  Map<String, dynamic> _asMap(dynamic value) {
    return JsonUtils.asMap(value);
  }

  Future<void> stop() async {
    await _listener.stop();
    await _listenerSubscription?.cancel();
    _listenerSubscription = null;
  }

  Future<void> dispose() async {
    await stop();
    await _listener.dispose();
    await _telemetryController.close();
    await _pcsTelemetryController.close();
    await _bmsTelemetryController.close();
    await _rawPacketController.close();
  }
}
