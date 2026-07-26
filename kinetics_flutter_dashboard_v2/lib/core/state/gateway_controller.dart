import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

import '../../models/gateway_models.dart';
import '../api/gateway_api_client.dart';

class GatewayController extends ChangeNotifier {
  GatewayController({GatewayApiClient? api})
      : api = api ?? GatewayApiClient();

  final GatewayApiClient api;
  final PlantSnapshot plant = PlantSnapshot();

  GatewaySession? session;
  bool busy = false;
  bool restConnected = false;
  bool wsConnected = false;
  String? errorMessage;
  String? lastEventMessage;

  Map<String, dynamic> health = <String, dynamic>{};
  Map<String, dynamic> storage = <String, dynamic>{};
  Map<String, dynamic> polling = <String, dynamic>{};
  Map<String, dynamic> dataRate = <String, dynamic>{};
  List<Map<String, dynamic>> activeAlarms = <Map<String, dynamic>>[];
  List<Map<String, dynamic>> assetMetadata = <Map<String, dynamic>>[];

  WebSocket? _telemetrySocket;
  StreamSubscription<dynamic>? _telemetrySubscription;
  Timer? _diagnosticTimer;
  Timer? _reconnectTimer;
  int _reconnectAttempt = 0;
  bool _disposed = false;

  bool get authenticated => session != null;
  bool get isInternal => session?.isInternal == true;

  Future<void> login({
    required String baseUrl,
    required String username,
    required String password,
  }) async {
    busy = true;
    errorMessage = null;
    notifyListeners();
    try {
      api.configure(baseUrl: baseUrl);
      final response = await api.login(username: username, password: password);
      final token = response['access_token']?.toString();
      if (token == null || token.isEmpty) {
        throw const ApiException('Login response did not contain an access token');
      }
      session = GatewaySession(
        baseUrl: api.baseUrl,
        token: token,
        username: response['username']?.toString() ?? username,
        role: response['role']?.toString() ?? 'customer',
      );
      api.configure(baseUrl: api.baseUrl, bearerToken: token);
      await bootstrap();
    } catch (error) {
      session = null;
      errorMessage = error.toString();
      rethrow;
    } finally {
      busy = false;
      if (!_disposed) notifyListeners();
    }
  }

  Future<void> bootstrap() async {
    await refreshCompact();
    await refreshDiagnostics();
    await refreshAlarms();
    await refreshAssetMetadata();
    await connectTelemetry();
    _diagnosticTimer?.cancel();
    _diagnosticTimer = Timer.periodic(
      const Duration(seconds: 8),
      (_) {
        refreshDiagnostics(silent: true);
      },
    );
  }

  Future<void> refreshCompact({bool silent = false}) async {
    if (!silent) {
      busy = true;
      notifyListeners();
    }
    try {
      final payload = await api.getJson('/api/telemetry/compact');
      plant.applyMessage(payload);
      restConnected = true;
      errorMessage = null;
    } catch (error) {
      restConnected = false;
      errorMessage = error.toString();
      if (!silent) rethrow;
    } finally {
      if (!silent) busy = false;
      if (!_disposed) notifyListeners();
    }
  }

  Future<void> forceCompleteExtraction() async {
    busy = true;
    errorMessage = null;
    notifyListeners();
    try {
      final payload = await api.getJson(
        '/api/telemetry/snapshot',
        query: const <String, String>{
          'refresh': 'true',
          'include_slow': 'true',
          'include_bulk': 'true',
        },
        timeout: const Duration(minutes: 5),
      );
      plant.applyMessage(payload);
      restConnected = true;
      lastEventMessage = 'Complete fast, normal, slow and bulk extraction finished.';
    } catch (error) {
      errorMessage = error.toString();
      rethrow;
    } finally {
      busy = false;
      if (!_disposed) notifyListeners();
    }
  }

  Future<void> refreshAssetMetadata() async {
    try {
      final payload = await api.getJson('/api/assets');
      final raw = payload['assets'];
      if (raw is List) {
        assetMetadata = raw
            .whereType<Map>()
            .map((item) => Map<String, dynamic>.from(item))
            .toList();
      }
    } catch (error) {
      errorMessage = error.toString();
    }
    if (!_disposed) notifyListeners();
  }

  Future<void> refreshAlarms({bool silent = false}) async {
    try {
      final payload = await api.getJson('/api/alarms');
      final raw = payload['alarms'];
      if (raw is List) {
        activeAlarms = raw
            .whereType<Map>()
            .map((item) => Map<String, dynamic>.from(item))
            .toList();
        plant.alarms = List<Map<String, dynamic>>.from(activeAlarms);
      }
    } catch (error) {
      if (!silent) errorMessage = error.toString();
    }
    if (!_disposed) notifyListeners();
  }

  Future<void> refreshDiagnostics({bool silent = false}) async {
    try {
      final results = await Future.wait<Map<String, dynamic>>(<Future<Map<String, dynamic>>>[
        api.getJson('/api/health'),
        api.getJson('/api/storage/status'),
        api.getJson('/api/diagnostics/polling'),
        api.getJson('/api/diagnostics/data-rate'),
      ]);
      health = results[0];
      storage = results[1];
      polling = results[2];
      dataRate = results[3];
      restConnected = true;
      await refreshAlarms(silent: true);
    } catch (error) {
      restConnected = false;
      if (!silent) errorMessage = error.toString();
    }
    if (!_disposed) notifyListeners();
  }

  Future<AssetSnapshot> loadRackDetails(int rackId) async {
    final payload = await api.getJson(
      '/api/bms/racks/$rackId/details',
      timeout: const Duration(minutes: 5),
    );
    final asset = AssetSnapshot.fromJson(payload);
    plant.assets[asset.assetId] = asset;
    notifyListeners();
    return asset;
  }

  Future<List<Map<String, dynamic>>> loadHistorian(
    String assetId, {
    int limit = 100,
  }) async {
    final payload = await api.getJson(
      '/api/historian/$assetId',
      query: <String, String>{'limit': '$limit'},
      timeout: const Duration(seconds: 60),
    );
    final raw = payload['samples'];
    if (raw is! List) return const <Map<String, dynamic>>[];
    return raw
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
  }

  Future<List<Map<String, dynamic>>> loadAlarmHistory({int limit = 500}) async {
    final payload = await api.getJson(
      '/api/alarms/history',
      query: <String, String>{'limit': '$limit'},
    );
    final raw = payload['history'];
    if (raw is! List) return const <Map<String, dynamic>>[];
    return raw
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
  }

  Future<Map<String, dynamic>> loadMockScenarios() {
    return api.getJson('/api/mock/scenarios');
  }

  Future<void> setMockScenario(String scenario) async {
    final result = await api.postJson('/api/mock/scenario/$scenario');
    lastEventMessage = result['scenario']?.toString() == null
        ? 'Mock scenario changed to $scenario.'
        : 'Mock scenario changed to ${result['scenario']}.';
    await refreshCompact(silent: true);
  }

  Future<void> connectTelemetry() async {
    await _closeSocket();
    try {
      final socket = await api.openTelemetrySocket(mode: 'delta');
      _telemetrySocket = socket;
      wsConnected = true;
      _reconnectAttempt = 0;
      _telemetrySubscription = socket.listen(
        _handleSocketData,
        onError: (Object error, StackTrace stack) {
          wsConnected = false;
          errorMessage = 'WebSocket: $error';
          notifyListeners();
          _scheduleReconnect();
        },
        onDone: () {
          wsConnected = false;
          notifyListeners();
          _scheduleReconnect();
        },
        cancelOnError: true,
      );
    } catch (error) {
      wsConnected = false;
      errorMessage = 'WebSocket connection failed: $error';
      _scheduleReconnect();
    }
    if (!_disposed) notifyListeners();
  }

  void _handleSocketData(dynamic data) {
    try {
      final decoded = jsonDecode(data.toString());
      if (decoded is Map) {
        plant.applyMessage(Map<String, dynamic>.from(decoded));
        final type = decoded['type']?.toString();
        if (type == 'telemetry_update') {
          lastEventMessage =
              '${decoded['poll_class'] ?? 'telemetry'} update, sequence ${decoded['sequence'] ?? plant.sequence}';
        } else {
          lastEventMessage = 'Live snapshot received.';
        }
      }
      wsConnected = true;
      errorMessage = null;
    } catch (error) {
      errorMessage = 'Invalid WebSocket payload: $error';
    }
    if (!_disposed) notifyListeners();
  }

  void _scheduleReconnect() {
    if (_disposed || session == null || _reconnectTimer?.isActive == true) return;
    _reconnectAttempt += 1;
    final exponent = _reconnectAttempt.clamp(0, 5).toInt();
    final seconds = (1 << exponent).clamp(2, 30).toInt();
    _reconnectTimer = Timer(Duration(seconds: seconds), () {
      connectTelemetry();
    });
  }

  Future<void> _closeSocket() async {
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    await _telemetrySubscription?.cancel();
    _telemetrySubscription = null;
    await _telemetrySocket?.close();
    _telemetrySocket = null;
    wsConnected = false;
  }

  Future<void> logout() async {
    _diagnosticTimer?.cancel();
    _diagnosticTimer = null;
    await _closeSocket();
    session = null;
    api.token = null;
    plant.assets.clear();
    activeAlarms = <Map<String, dynamic>>[];
    health = <String, dynamic>{};
    storage = <String, dynamic>{};
    polling = <String, dynamic>{};
    dataRate = <String, dynamic>{};
    restConnected = false;
    errorMessage = null;
    lastEventMessage = null;
    notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _diagnosticTimer?.cancel();
    _reconnectTimer?.cancel();
    _telemetrySubscription?.cancel();
    _telemetrySocket?.close();
    api.close();
    super.dispose();
  }
}
