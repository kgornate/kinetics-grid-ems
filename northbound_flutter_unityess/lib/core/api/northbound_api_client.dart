
import 'dart:convert';

import 'package:http/http.dart' as http;

class NorthboundApiClient {
  NorthboundApiClient({
    required this.baseUrl,
    this.token,
    http.Client? client,
  }) : _client = client ?? http.Client();

  final String baseUrl;
  final String? token;
  final http.Client _client;

  Map<String, String> _headers({bool json = false}) {
    final headers = <String, String>{};
    if (json) headers['Content-Type'] = 'application/json';
    if (token != null && token!.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
    }
    return headers;
  }

  Uri _uri(String path, [Map<String, dynamic>? query]) {
    final root = Uri.parse(baseUrl);
    return root.replace(
      path: path.startsWith('/') ? path : '/$path',
      queryParameters: query == null
          ? null
          : query.map((key, value) => MapEntry(key, '$value')),
    );
  }

  Future<Map<String, dynamic>> login({
    required String username,
    required String password,
  }) async {
    final response = await _client.post(
      _uri('/api/auth/login'),
      headers: _headers(json: true),
      body: jsonEncode({
        'username': username,
        'password': password,
      }),
    );
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getHealth() async {
    final response = await _client.get(_uri('/api/health'), headers: _headers());
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getSourcesSummary() async {
    final response = await _client.get(
      _uri('/api/sources/summary'),
      headers: _headers(),
    );
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getAssets({String? sourceId}) async {
    final response = await _client.get(
      _uri('/api/assets', sourceId == null ? null : {'source_id': sourceId}),
      headers: _headers(),
    );
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getAssetTelemetry(
    String assetId, {
    bool compact = true,
    bool keyOnly = false,
    String? category,
    int? page,
    int? pageSize,
  }) async {
    final query = <String, dynamic>{
      'compact': compact,
      'key_only': keyOnly,
    };
    if (category != null && category.isNotEmpty) query['category'] = category;
    if (page != null) query['page'] = page;
    if (pageSize != null) query['page_size'] = pageSize;

    final response = await _client.get(
      _uri('/api/assets/$assetId/telemetry', query),
      headers: _headers(),
    );
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getKeySignals() async {
    final response = await _client.get(
      _uri('/api/telemetry/key-signals'),
      headers: _headers(),
    );
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getAlarms() async {
    final response = await _client.get(_uri('/api/alarms'), headers: _headers());
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getFastBessStatus() async {
    final response = await _client.get(
      _uri('/api/fast-bess/status'),
      headers: _headers(),
    );
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getFastBessProfile() async {
    final response = await _client.get(
      _uri('/api/fast-bess/profile'),
      headers: _headers(),
    );
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getFastBessLatest({
    String format = 'compact',
  }) async {
    final response = await _client.get(
      _uri('/api/fast-bess/latest', {'format': format}),
      headers: _headers(),
    );
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getFastBessHistory({
    String? sourceId,
    int? fromEpochMs,
    int? toEpochMs,
    int limit = 100,
    String order = 'desc',
    String format = 'compact',
  }) async {
    final query = <String, dynamic>{
      'limit': limit,
      'order': order,
      'format': format,
    };
    if (sourceId != null && sourceId.isNotEmpty) {
      query['source_id'] = sourceId;
    }
    if (fromEpochMs != null) query['from_epoch_ms'] = fromEpochMs;
    if (toEpochMs != null) query['to_epoch_ms'] = toEpochMs;

    final response = await _client.get(
      _uri('/api/fast-bess/history', query),
      headers: _headers(),
    );
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getControllerStatus() async {
    final response = await _client.get(
      _uri('/api/controller/status'),
      headers: _headers(),
    );
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getControllerHistory({
    int limit = 50,
    int offset = 0,
    String order = 'desc',
    String? eventType,
    String? severity,
    String? device,
    String? result,
    String? fromTime,
    String? toTime,
  }) async {
    final query = <String, dynamic>{
      'limit': limit,
      'offset': offset,
      'order': order,
    };
    if (eventType != null && eventType.isNotEmpty) query['event_type'] = eventType;
    if (severity != null && severity.isNotEmpty) query['severity'] = severity;
    if (device != null && device.isNotEmpty) query['device'] = device;
    if (result != null && result.isNotEmpty) query['result'] = result;
    if (fromTime != null && fromTime.isNotEmpty) query['from_time'] = fromTime;
    if (toTime != null && toTime.isNotEmpty) query['to_time'] = toTime;

    final response = await _client.get(
      _uri('/api/controller/history', query),
      headers: _headers(),
    );
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getSolisStatus() async {
    final response = await _client.get(
      _uri('/api/solis/status'),
      headers: _headers(),
    );
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getSolisHistory({
    int limit = 50,
    int offset = 0,
    String order = 'desc',
    String? eventType,
    String? result,
  }) async {
    final query = <String, dynamic>{
      'limit': limit,
      'offset': offset,
      'order': order,
    };
    if (eventType != null && eventType.isNotEmpty) query['event_type'] = eventType;
    if (result != null && result.isNotEmpty) query['result'] = result;

    final response = await _client.get(
      _uri('/api/solis/history', query),
      headers: _headers(),
    );
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getControllerSettings() async {
    final response = await _client.get(
      _uri('/api/controller/settings'),
      headers: _headers(),
    );
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> updateControllerSettings({
    double? highLimit,
    double? recoveryLimit,
    double? lowCutoffLimit,
    double? lowRecoveryLimit,
  }) async {
    final body = <String, dynamic>{};
    if (highLimit != null) body['high_limit'] = highLimit;
    if (recoveryLimit != null) body['recovery_limit'] = recoveryLimit;
    if (lowCutoffLimit != null) body['low_cutoff_limit'] = lowCutoffLimit;
    if (lowRecoveryLimit != null) body['low_recovery_limit'] = lowRecoveryLimit;

    final response = await _client.patch(
      _uri('/api/admin/controller/settings'),
      headers: _headers(json: true),
      body: jsonEncode(body),
    );
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  void _throwIfNeeded(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) return;
    throw Exception('HTTP ${response.statusCode}: ${response.body}');
  }

  void dispose() => _client.close();
}
