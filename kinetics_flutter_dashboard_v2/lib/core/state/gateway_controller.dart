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

  ControlSequenceCapabilities? controlCapabilities;
  ControlSequenceStatus? controlStatus;
  final Map<String, ControlSequenceStatus> controlStatuses =
      <String, ControlSequenceStatus>{};
  Map<String, dynamic> controlPlantSummary = <String, dynamic>{};
  Map<String, dynamic> lastControlResponse = <String, dynamic>{};
  final Set<String> _controlBusyPairs = <String>{};
  String selectedControlPair = 'pair_1';

  WebSocket? _telemetrySocket;
  StreamSubscription<dynamic>? _telemetrySubscription;
  Timer? _diagnosticTimer;
  Timer? _controlTimer;
  Timer? _reconnectTimer;
  int _reconnectAttempt = 0;
  bool _controlStatusInFlight = false;
  bool _controlStatusRefreshPending = false;
  bool _controlPollingEnabled = false;
  int _controlStatusGeneration = 0;
  int controlStatusSkippedRefreshes = 0;
  DateTime? controlStatusReceivedAt;
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
    if (isInternal) {
      await refreshControlCapabilities(silent: true);
      await refreshControlStatus(silent: true);
    }
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

  Future<void> refreshControlCapabilities({bool silent = false}) async {
    if (!isInternal) return;
    try {
      final payload =
          await api.getJson('/api/control-sequence/capabilities');
      controlCapabilities = ControlSequenceCapabilities.fromJson(payload);
      final enabledPairs = controlCapabilities!.pairs
          .where((pair) => pair.enabled)
          .map((pair) => pair.pairId)
          .toList();
      if (enabledPairs.isNotEmpty &&
          !enabledPairs.contains(selectedControlPair)) {
        selectedControlPair = enabledPairs.first;
      }
    } catch (error) {
      if (!silent) errorMessage = error.toString();
      if (!silent) rethrow;
    } finally {
      if (!_disposed) notifyListeners();
    }
  }

  Future<void> refreshControlStatus({bool silent = false}) async {
    if (!isInternal || _disposed) return;

    // Multi-pair overview polling is cache-only and single-flight. It never
    // requests direct Modbus reads, so telemetry display cannot compete with
    // startup, safe-stop or runtime safety monitoring.
    if (_controlStatusInFlight) {
      _controlStatusRefreshPending = true;
      controlStatusSkippedRefreshes += 1;
      return;
    }

    _controlStatusInFlight = true;
    final generation = _controlStatusGeneration;
    try {
      final payload = await api.getJson(
        '/api/control-sequence/status/all',
        timeout: const Duration(seconds: 10),
      );
      if (_disposed || generation != _controlStatusGeneration) return;

      final parsed = <String, ControlSequenceStatus>{};
      final byPair = payload['by_pair_id'];
      if (byPair is Map) {
        for (final entry in byPair.entries) {
          if (entry.value is Map) {
            final status = ControlSequenceStatus.fromJson(
              Map<String, dynamic>.from(entry.value as Map),
            );
            parsed[entry.key.toString()] = status;
          }
        }
      } else {
        final pairs = payload['pairs'];
        if (pairs is List) {
          for (final item in pairs.whereType<Map>()) {
            final status = ControlSequenceStatus.fromJson(
              Map<String, dynamic>.from(item),
            );
            parsed[status.pairId] = status;
          }
        }
      }

      controlStatuses
        ..clear()
        ..addAll(parsed);
      controlPlantSummary = payload['summary'] is Map
          ? Map<String, dynamic>.from(payload['summary'] as Map)
          : <String, dynamic>{};
      controlStatus = controlStatuses[selectedControlPair];
      controlStatusReceivedAt = DateTime.now().toUtc();
      restConnected = true;
    } catch (error) {
      if (!silent) errorMessage = error.toString();
      if (!silent) rethrow;
    } finally {
      _controlStatusInFlight = false;
      final runPending = _controlStatusRefreshPending && !_disposed;
      _controlStatusRefreshPending = false;
      if (!_disposed) notifyListeners();
      if (runPending) {
        unawaited(refreshControlStatus(silent: true));
      }
    }
  }

  Future<void> refreshSelectedControlStatusFresh({bool silent = false}) async {
    if (!isInternal || _disposed) return;
    final pairId = selectedControlPair;
    try {
      final payload = await api.getJson(
        '/api/control-sequence/$pairId/status',
        query: const <String, String>{'fresh': 'true'},
        timeout: const Duration(seconds: 120),
      );
      if (_disposed || pairId != selectedControlPair) return;
      final status = ControlSequenceStatus.fromJson(payload);
      controlStatuses[pairId] = status;
      controlStatus = status;
      controlStatusReceivedAt = DateTime.now().toUtc();
      restConnected = true;
    } catch (error) {
      if (!silent) errorMessage = error.toString();
      if (!silent) rethrow;
    } finally {
      if (!_disposed) notifyListeners();
    }
  }

  void selectControlPair(String pairId) {
    if (pairId == selectedControlPair) return;
    selectedControlPair = pairId;
    controlStatus = controlStatuses[pairId];
    controlStatusReceivedAt = controlStatus == null ? null : DateTime.now().toUtc();
    _controlStatusGeneration += 1;
    notifyListeners();
    unawaited(refreshControlStatus(silent: true));
  }

  void startControlPolling() {
    if (!isInternal || _disposed) return;
    _controlPollingEnabled = true;
    _controlTimer?.cancel();
    unawaited(refreshControlStatus(silent: true));
    _controlTimer = Timer.periodic(
      const Duration(seconds: 2),
      (_) {
        if (_controlPollingEnabled) {
          unawaited(refreshControlStatus(silent: true));
        }
      },
    );
  }

  void stopControlPolling() {
    _controlPollingEnabled = false;
    _controlTimer?.cancel();
    _controlTimer = null;
    _controlStatusRefreshPending = false;
  }

  bool get controlPollingActive =>
      _controlPollingEnabled && _controlTimer?.isActive == true;

  bool get controlStatusRequestActive => _controlStatusInFlight;

  bool get controlBusy => _controlBusyPairs.contains(selectedControlPair);

  bool get anyControlBusy => _controlBusyPairs.isNotEmpty;

  bool isControlPairBusy(String pairId) => _controlBusyPairs.contains(pairId);

  ControlSequenceStatus? controlStatusFor(String pairId) =>
      controlStatuses[pairId];

  double get totalControlSetpointKw =>
      _asControllerDouble(controlPlantSummary['total_setpoint_kw']) ?? 0.0;

  double get totalControlActualPowerKw =>
      _asControllerDouble(controlPlantSummary['total_actual_power_kw']) ?? 0.0;

  String get controlStatusSource {
    final refresh = controlStatus?.raw['refresh'];
    if (refresh is Map) {
      return refresh['source']?.toString() ?? 'cached_runtime';
    }
    return 'cached_runtime';
  }

  bool get controlStatusIsStale {
    final refresh = controlStatus?.raw['refresh'];
    if (refresh is Map && refresh['stale'] == true) return true;
    final timestamp = controlStatus?.timestamp;
    final parsed = timestamp == null ? null : DateTime.tryParse(timestamp);
    if (parsed == null) return controlStatus == null;
    return DateTime.now().toUtc().difference(parsed.toUtc()) >
        const Duration(seconds: 20);
  }

  Duration? get controlStatusAge {
    final timestamp = controlStatus?.timestamp;
    final parsed = timestamp == null ? null : DateTime.tryParse(timestamp);
    if (parsed == null) return null;
    final age = DateTime.now().toUtc().difference(parsed.toUtc());
    return age.isNegative ? Duration.zero : age;
  }

  Future<Map<String, dynamic>> automaticStart({
    required String direction,
    required double targetPowerKw,
    double? rampStepKw,
    double? rampIntervalSeconds,
  }) {
    final phrase = controlCapabilities?.automaticConfirmationPhrase ??
        'EXECUTE_AUTOMATIC_SEQUENCE';
    return _executeControl(
      '/api/control-sequence/$selectedControlPair/automatic-start',
      <String, dynamic>{
        'direction': direction,
        'power_kw': targetPowerKw,
        'ramp_step_kw': rampStepKw,
        'ramp_interval_seconds': rampIntervalSeconds,
        'confirmation': phrase,
      },
      successMessage:
          'Automatic $direction sequence accepted at ${targetPowerKw.toStringAsFixed(1)} kW.',
    );
  }

  Future<Map<String, dynamic>> nextControlStep({
    required String direction,
    required double targetPowerKw,
  }) {
    return _executeControl(
      '/api/control-sequence/$selectedControlPair/next-step',
      <String, dynamic>{
        'direction': direction,
        'power_kw': targetPowerKw,
        'confirmation': _stageConfirmation,
      },
      successMessage: 'Commissioning step executed.',
    );
  }

  Future<Map<String, dynamic>> setControlPower({
    required String direction,
    required double powerKw,
  }) {
    return _executeControl(
      '/api/control-sequence/$selectedControlPair/set-power',
      <String, dynamic>{
        'direction': direction,
        'power_kw': powerKw,
        'confirmation': _stageConfirmation,
      },
      successMessage:
          '${direction == 'charge' ? 'Charge' : 'Discharge'} setpoint sent: ${powerKw.toStringAsFixed(1)} kW.',
    );
  }

  Future<Map<String, dynamic>> zeroControlPower() {
    return _executeControl(
      '/api/control-sequence/$selectedControlPair/zero-power',
      <String, dynamic>{'confirmation': _stageConfirmation},
      successMessage: 'Zero-power command sent and verified.',
    );
  }

  Future<Map<String, dynamic>> safeStopControl({bool openBms = true}) {
    return _executeControl(
      '/api/control-sequence/$selectedControlPair/safe-stop',
      <String, dynamic>{
        'confirmation': _stageConfirmation,
        'open_bms': openBms,
      },
      successMessage: openBms
          ? 'Safe shutdown completed; PCS stopped and BMS opened.'
          : 'PCS safe stop completed.',
      timeout: const Duration(seconds: 60),
    );
  }

  Future<Map<String, dynamic>> safeStopAllControl({bool openBms = true}) async {
    if (!isInternal) {
      throw const ApiException('Internal role is required for control');
    }
    if (_controlBusyPairs.isNotEmpty) {
      throw const ApiException(
        'Wait for active pair commands to finish before Safe Stop All.',
      );
    }
    final pairIds = controlCapabilities?.pairs
            .where((pair) => pair.enabled)
            .map((pair) => pair.pairId)
            .toSet() ??
        <String>{'pair_1', 'pair_2', 'pair_3', 'pair_4'};
    _controlBusyPairs.addAll(pairIds);
    errorMessage = null;
    notifyListeners();
    try {
      final result = await api.postJson(
        '/api/control-sequence/safe-stop-all',
        body: <String, dynamic>{
          'confirmation': _stageConfirmation,
          'open_bms': openBms,
        },
        timeout: const Duration(minutes: 5),
      );
      lastControlResponse = result;
      lastEventMessage = result['ok'] == true
          ? 'All enabled pairs were safely stopped.'
          : 'Safe Stop All completed with one or more pair failures.';
      await refreshControlStatus(silent: true);
      return result;
    } catch (error) {
      errorMessage = error.toString();
      rethrow;
    } finally {
      _controlBusyPairs.removeAll(pairIds);
      if (!_disposed) notifyListeners();
    }
  }

  Future<Map<String, dynamic>> abortControl({bool openBms = true}) {
    return _executeControl(
      '/api/control-sequence/$selectedControlPair/abort',
      <String, dynamic>{
        'confirmation': _stageConfirmation,
        'open_bms': openBms,
      },
      successMessage: 'Sequence abort requested and safe-stop executed.',
      timeout: const Duration(seconds: 60),
    );
  }

  String get _stageConfirmation =>
      controlCapabilities?.confirmationPhrase ?? 'EXECUTE_STAGE_WRITE';

  Future<Map<String, dynamic>> _executeControl(
    String path,
    Map<String, dynamic> body, {
    required String successMessage,
    Duration timeout = const Duration(seconds: 150),
  }) async {
    if (!isInternal) {
      throw const ApiException('Internal role is required for control');
    }
    final pairId = selectedControlPair;
    if (_controlBusyPairs.contains(pairId)) {
      throw ApiException(
        'A control command is already in progress for $pairId.',
      );
    }
    _controlBusyPairs.add(pairId);
    errorMessage = null;
    notifyListeners();
    try {
      body.removeWhere((key, value) => value == null);
      final result = await api.postJson(path, body: body, timeout: timeout);
      lastControlResponse = result;
      lastEventMessage = successMessage;
      await refreshControlStatus(silent: true);
      return result;
    } catch (error) {
      errorMessage = error.toString();
      rethrow;
    } finally {
      _controlBusyPairs.remove(pairId);
      if (!_disposed) notifyListeners();
    }
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
    stopControlPolling();
    await _closeSocket();
    session = null;
    api.token = null;
    plant.assets.clear();
    activeAlarms = <Map<String, dynamic>>[];
    assetMetadata = <Map<String, dynamic>>[];
    controlCapabilities = null;
    controlStatus = null;
    controlStatuses.clear();
    controlPlantSummary = <String, dynamic>{};
    controlStatusReceivedAt = null;
    _controlBusyPairs.clear();
    _controlStatusInFlight = false;
    _controlStatusRefreshPending = false;
    _controlPollingEnabled = false;
    _controlStatusGeneration += 1;
    controlStatusSkippedRefreshes = 0;
    lastControlResponse = <String, dynamic>{};
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
    _controlTimer?.cancel();
    _reconnectTimer?.cancel();
    _telemetrySubscription?.cancel();
    _telemetrySocket?.close();
    api.close();
    super.dispose();
  }
}


double? _asControllerDouble(dynamic value) {
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString() ?? '');
}
