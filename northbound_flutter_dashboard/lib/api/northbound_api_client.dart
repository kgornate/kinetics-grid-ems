import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/alarm_record.dart';
import '../models/auth_session.dart';
import '../models/api_result.dart';
import '../models/asset_summary.dart';
import '../models/log_filter_options.dart';
import '../models/log_record.dart';
import '../models/storage_status.dart';
import '../models/source_summary.dart';
import '../models/ems_command_register.dart';
import '../models/control_command_result.dart';

class LogQuery {
  const LogQuery({
    this.severity,
    this.eventType,
    this.source,
    this.assetId,
    this.fromTime,
    this.toTime,
    this.search,
    this.limit = 100,
    this.offset = 0,
    this.order = 'desc',
  });

  final String? severity;
  final String? eventType;
  final String? source;
  final String? assetId;
  final String? fromTime;
  final String? toTime;
  final String? search;
  final int limit;
  final int offset;
  final String order;

  Map<String, String> toQuery({bool includeLimit = true}) {
    final q = <String, String>{
      'order': order,
      if (includeLimit) 'limit': limit.toString(),
      if (offset > 0) 'offset': offset.toString(),
    };
    void add(String key, String? value) {
      final v = value?.trim();
      if (v != null && v.isNotEmpty) q[key] = v;
    }

    add('severity', severity);
    add('event_type', eventType);
    add('source', source);
    add('asset_id', assetId);
    add('from_time', fromTime);
    add('to_time', toTime);
    add('search', search);
    return q;
  }

  LogQuery copyWith({
    String? severity,
    String? eventType,
    String? source,
    String? assetId,
    String? fromTime,
    String? toTime,
    String? search,
    int? limit,
    int? offset,
    String? order,
    bool clearSeverity = false,
    bool clearEventType = false,
    bool clearSource = false,
    bool clearAssetId = false,
    bool clearFromTime = false,
    bool clearToTime = false,
    bool clearSearch = false,
  }) {
    return LogQuery(
      severity: clearSeverity ? null : severity ?? this.severity,
      eventType: clearEventType ? null : eventType ?? this.eventType,
      source: clearSource ? null : source ?? this.source,
      assetId: clearAssetId ? null : assetId ?? this.assetId,
      fromTime: clearFromTime ? null : fromTime ?? this.fromTime,
      toTime: clearToTime ? null : toTime ?? this.toTime,
      search: clearSearch ? null : search ?? this.search,
      limit: limit ?? this.limit,
      offset: offset ?? this.offset,
      order: order ?? this.order,
    );
  }
}

class LogQueryResult {
  const LogQueryResult({required this.total, required this.limit, required this.offset, required this.items});

  final int total;
  final int limit;
  final int offset;
  final List<LogRecord> items;

  factory LogQueryResult.fromJson(Map<String, dynamic> json) {
    final rawItems = json['items'];
    return LogQueryResult(
      total: _asInt(json['total']),
      limit: _asInt(json['limit']),
      offset: _asInt(json['offset']),
      items: rawItems is List
          ? rawItems.whereType<Map>().map((item) => LogRecord.fromJson(Map<String, dynamic>.from(item))).toList()
          : const [],
    );
  }

  static int _asInt(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '') ?? 0;
  }
}

class NorthboundApiClient {
  NorthboundApiClient({
    required this.restBaseUrl,
    required this.logsBaseUrl,
    required this.httpTimeout,
    this.accessToken,
    this.onUnauthorized,
  });

  final String restBaseUrl;
  final String logsBaseUrl;
  final Duration httpTimeout;
  String? accessToken;
  final void Function()? onUnauthorized;

  void setAccessToken(String? token) {
    accessToken = token;
  }

  Map<String, String> _headers() {
    final token = accessToken?.trim();
    return {
      'Accept': 'application/json',
      if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
    };
  }

  Map<String, String> _jsonHeaders() => {
        ..._headers(),
        'Content-Type': 'application/json',
      };

  String _baseForPath(String path) {
    // NorthBound v0.5 exposes /api/logs on the main REST API. The profile
    // still keeps logsBaseUrl configurable for sites that later route logs
    // through a separate tunnel/domain.
    final selected = path.startsWith('/api/logs') ? logsBaseUrl : restBaseUrl;
    return selected.endsWith('/') ? selected.substring(0, selected.length - 1) : selected;
  }

  Uri _uri(String path, [Map<String, String>? query]) {
    final cleanBase = _baseForPath(path);
    return Uri.parse('$cleanBase$path').replace(queryParameters: query);
  }

  String urlFor(String path, [Map<String, String>? query]) => _uri(path, query).toString();


  Future<ApiResult<AuthSession>> login({required String username, required String password}) async {
    try {
      final uri = _uri('/api/auth/login');
      final response = await http
          .post(
            uri,
            headers: _jsonHeaders(),
            body: jsonEncode({'username': username, 'password': password}),
          )
          .timeout(httpTimeout);
      if (response.statusCode < 200 || response.statusCode >= 300) {
        return ApiResult.failure('Login failed: HTTP ${response.statusCode}: ${response.body}');
      }
      final decoded = jsonDecode(response.body);
      if (decoded is! Map) return const ApiResult.failure('Login response is not a JSON object');
      final session = AuthSession.fromJson(Map<String, dynamic>.from(decoded));
      if (session.accessToken.isEmpty) return const ApiResult.failure('Login response did not include access token');
      setAccessToken(session.accessToken);
      return ApiResult.success(session);
    } catch (e) {
      return ApiResult.failure('Login request failed after ${httpTimeout.inSeconds}s: $e');
    }
  }

  Future<ApiResult<Map<String, dynamic>>> getMe() async => _getJson('/api/auth/me');


  Future<ApiResult<Map<String, dynamic>>> getHealth() async => _getJson('/api/health');


  Future<ApiResult<List<SourceSummary>>> getSources() async {
    final result = await _getJson('/api/sources');
    if (!result.isSuccess) return ApiResult.failure(result.error ?? 'Failed to read sources');
    return _parseSourceList(result.data ?? {});
  }

  Future<ApiResult<List<SourceSummary>>> getSourceSummary() async {
    final result = await _getJson('/api/sources/summary');
    if (!result.isSuccess) return ApiResult.failure(result.error ?? 'Failed to read source summary');
    return _parseSourceList(result.data ?? {});
  }

  Future<ApiResult<List<AssetSummary>>> getSourceAssets(String sourceId) async {
    final result = await _getJson('/api/sources/$sourceId/assets');
    if (!result.isSuccess) return ApiResult.failure(result.error ?? 'Failed to read assets for $sourceId');
    return _parseAssetList(result.data ?? {});
  }

  Future<ApiResult<Map<String, dynamic>>> getSourceTelemetry(String sourceId) => _getJson('/api/sources/$sourceId/telemetry');

  Future<ApiResult<List<AssetSummary>>> getAssets() async {
    final result = await _getJson('/api/assets');
    if (!result.isSuccess) return ApiResult.failure(result.error ?? 'Failed to read assets');
    return _parseAssetList(result.data ?? {});
  }

  Future<ApiResult<Map<String, dynamic>>> getKeySignals({String? sourceId}) {
    final query = sourceId == null || sourceId.trim().isEmpty ? null : {'source_id': sourceId.trim()};
    return _getJson('/api/telemetry/key-signals', query);
  }

  Future<ApiResult<Map<String, dynamic>>> getAssetTelemetry(String assetId, {String? category}) async {
    final query = category == null || category.isEmpty ? null : {'category': category};
    return _getJson('/api/assets/$assetId/telemetry', query);
  }

  Future<ApiResult<List<AlarmRecord>>> getAlarms({String? sourceId}) async {
    final query = sourceId == null || sourceId.trim().isEmpty ? null : {'source_id': sourceId.trim()};
    final result = await _getJson('/api/alarms', query);
    if (!result.isSuccess) return ApiResult.failure(result.error ?? 'Failed to read alarms');
    final data = result.data ?? {};

    // Gateway v0.5 returns {"active_count": n, "items": [...]}. Older
    // builds returned {"alarms": [...]}. Support both shapes.
    final rawAlarms = data['alarms'] ?? data['items'] ?? data['active_alarms'];
    if (rawAlarms is List) {
      return ApiResult.success(
        rawAlarms.whereType<Map>().map((item) => AlarmRecord.fromJson(Map<String, dynamic>.from(item))).toList(),
      );
    }
    return const ApiResult.success([]);
  }

  Future<ApiResult<StorageStatus>> getStorageStatus() async {
    final result = await _getJson('/api/storage/status');
    if (!result.isSuccess) return ApiResult.failure(result.error ?? 'Failed to read storage status');
    return ApiResult.success(StorageStatus.fromJson(result.data ?? {}));
  }

  Future<ApiResult<StorageStatus>> getStorageHealth() async {
    final result = await _getJson('/api/storage/health');
    if (!result.isSuccess) return ApiResult.failure(result.error ?? 'Failed to read storage health');
    return ApiResult.success(StorageStatus.fromJson(result.data ?? {}));
  }

  Future<ApiResult<LogFilterOptions>> getLogFilterOptions() async {
    final result = await _getJson('/api/logs/filters');
    if (!result.isSuccess) return ApiResult.failure(result.error ?? 'Failed to read log filter options');
    return ApiResult.success(LogFilterOptions.fromJson(result.data ?? {}));
  }

  Future<ApiResult<Map<String, dynamic>>> getLogSummary({String? fromTime, String? toTime}) async {
    final query = <String, String>{};
    if (fromTime != null && fromTime.trim().isNotEmpty) query['from_time'] = fromTime.trim();
    if (toTime != null && toTime.trim().isNotEmpty) query['to_time'] = toTime.trim();
    return _getJson('/api/logs/summary', query.isEmpty ? null : query);
  }

  Future<ApiResult<LogQueryResult>> getLogs(LogQuery query) async {
    final result = await _getJson('/api/logs', query.toQuery());
    if (!result.isSuccess) return ApiResult.failure(result.error ?? 'Failed to query logs');
    return ApiResult.success(LogQueryResult.fromJson(result.data ?? {}));
  }

  String logExportUrl(LogQuery query) => urlFor('/api/logs/export.csv', query.toQuery(includeLimit: false));


  Future<ApiResult<Map<String, dynamic>>> getRuntimeConfig() async => _getJson('/api/config/runtime');

  Future<ApiResult<Map<String, dynamic>>> updateRuntimeConfig({required String section, required Map<String, dynamic> values}) async {
    try {
      final uri = _uri('/api/config/runtime');
      final response = await http
          .post(
            uri,
            headers: _jsonHeaders(),
            body: jsonEncode({'section': section, 'values': values}),
          )
          .timeout(httpTimeout);
      if (response.statusCode == 401) {
        onUnauthorized?.call();
        return ApiResult.failure('Unauthorized. Please login again.');
      }
      if (response.statusCode == 403) return ApiResult.failure('Forbidden for current login role.');
      if (response.statusCode < 200 || response.statusCode >= 300) {
        return ApiResult.failure('HTTP ${response.statusCode}: ${response.body}');
      }
      final decoded = jsonDecode(response.body);
      if (decoded is! Map) return const ApiResult.failure('Response is not a JSON object');
      return ApiResult.success(Map<String, dynamic>.from(decoded));
    } catch (e) {
      return ApiResult.failure('Config update failed after ${httpTimeout.inSeconds}s: $e');
    }
  }

  Future<ApiResult<Map<String, dynamic>>> getSnapshots({String? assetId, int limit = 20}) async {
    final query = <String, String>{'limit': limit.toString()};
    if (assetId != null && assetId.trim().isNotEmpty) query['asset_id'] = assetId.trim();
    return _getJson('/api/storage/snapshots', query);
  }

  Future<ApiResult<Map<String, dynamic>>> getPoints({required String assetId, required String signalName, int limit = 100}) async {
    return _getJson('/api/storage/points', {'asset_id': assetId, 'signal_name': signalName, 'limit': limit.toString()});
  }


  Future<ApiResult<List<EmsCommandRegister>>> getEmsCommandRegisters({required String sourceId}) async {
    final result = await _getJson('/api/commands/ems/registers', {'source_id': sourceId});
    if (!result.isSuccess) return ApiResult.failure(result.error ?? 'Failed to read command registers');
    final data = result.data ?? {};
    final raw = data['items'] ?? data['registers'] ?? data['commands'] ?? data['data'];
    if (raw is List) {
      return ApiResult.success(raw.whereType<Map>().map((item) => EmsCommandRegister.fromJson(Map<String, dynamic>.from(item))).toList());
    }
    if (raw is Map) {
      return ApiResult.success(raw.entries.where((entry) => entry.value is Map).map((entry) {
        final item = Map<String, dynamic>.from(entry.value as Map);
        item.putIfAbsent('signal_name', () => entry.key.toString());
        return EmsCommandRegister.fromJson(item);
      }).toList());
    }
    return const ApiResult.success([]);
  }

  Future<ApiResult<Map<String, dynamic>>> writeEmsRegister({
    required String sourceId,
    required String signalName,
    required num value,
    bool readback = true,
    String? note,
  }) {
    return _postJson('/api/commands/ems/write', {
      'source_id': sourceId,
      'signal_name': signalName,
      'value': value,
      'readback': readback,
      if (note != null && note.trim().isNotEmpty) 'note': note.trim(),
    });
  }

  Future<ApiResult<ControlCommandResult>> setSourceGridMode({
    required String sourceId,
    required String targetMode,
    bool readback = true,
    int timeoutSec = 60,
    String? note,
  }) async {
    final result = await _postJson('/api/control/sources/$sourceId/grid-mode', {
      'target_mode': targetMode,
      'readback': readback,
      'timeout_sec': timeoutSec,
      if (note != null && note.trim().isNotEmpty) 'note': note.trim(),
    });
    if (!result.isSuccess) return ApiResult.failure(result.error ?? 'Grid-mode command failed');
    return ApiResult.success(ControlCommandResult.fromJson(result.data ?? {}));
  }

  Future<ApiResult<ControlCommandResult>> standbySource({required String sourceId, bool readback = true, String? note}) async {
    final result = await _postJson('/api/control/sources/$sourceId/standby', {
      'readback': readback,
      if (note != null && note.trim().isNotEmpty) 'note': note.trim(),
    });
    if (!result.isSuccess) return ApiResult.failure(result.error ?? 'Standby command failed');
    return ApiResult.success(ControlCommandResult.fromJson(result.data ?? {}));
  }

  Future<ApiResult<ControlCommandResult>> chargeSource({required String sourceId, required num powerKw, bool readback = true, String? note}) async {
    final result = await _postJson('/api/control/sources/$sourceId/charge', {
      'power_kw': powerKw,
      'readback': readback,
      if (note != null && note.trim().isNotEmpty) 'note': note.trim(),
    });
    if (!result.isSuccess) return ApiResult.failure(result.error ?? 'Charge command failed');
    return ApiResult.success(ControlCommandResult.fromJson(result.data ?? {}));
  }

  Future<ApiResult<ControlCommandResult>> dischargeSource({required String sourceId, required num powerKw, bool readback = true, String? note}) async {
    final result = await _postJson('/api/control/sources/$sourceId/discharge', {
      'power_kw': powerKw,
      'readback': readback,
      if (note != null && note.trim().isNotEmpty) 'note': note.trim(),
    });
    if (!result.isSuccess) return ApiResult.failure(result.error ?? 'Discharge command failed');
    return ApiResult.success(ControlCommandResult.fromJson(result.data ?? {}));
  }

  Future<ApiResult<ControlCommandResult>> setSiteGridMode({
    required String targetMode,
    List<String>? sourceIds,
    List<String>? sourceOrder,
    bool readback = true,
    int timeoutSec = 60,
    bool waitForVoltageStable = true,
    String? note,
  }) async {
    final body = <String, dynamic>{
      'target_mode': targetMode,
      'readback': readback,
      'timeout_sec': timeoutSec,
      'wait_for_voltage_stable': waitForVoltageStable,
      if (sourceIds != null && sourceIds.isNotEmpty) 'source_ids': sourceIds,
      if (sourceOrder != null && sourceOrder.isNotEmpty) 'source_order': sourceOrder,
      if (note != null && note.trim().isNotEmpty) 'note': note.trim(),
    };
    final result = await _postJson('/api/control/site/grid-mode', body);
    if (!result.isSuccess) return ApiResult.failure(result.error ?? 'Site grid-mode command failed');
    return ApiResult.success(ControlCommandResult.fromJson(result.data ?? {}));
  }

  Future<ApiResult<ControlCommandResult>> standbySite({required List<String> sourceIds, bool readback = true, String? note}) async {
    final result = await _postJson('/api/control/site/standby', {
      'source_ids': sourceIds,
      'readback': readback,
      if (note != null && note.trim().isNotEmpty) 'note': note.trim(),
    });
    if (!result.isSuccess) return ApiResult.failure(result.error ?? 'Site standby command failed');
    return ApiResult.success(ControlCommandResult.fromJson(result.data ?? {}));
  }

  Future<ApiResult<ControlCommandResult>> setSitePower({
    required String operation,
    required num totalPowerKw,
    required List<String> sourceIds,
    String allocation = 'equal',
    bool readback = true,
    String? note,
  }) async {
    final result = await _postJson('/api/control/site/power', {
      'operation': operation,
      'total_power_kw': totalPowerKw,
      'source_ids': sourceIds,
      'allocation': allocation,
      'readback': readback,
      if (note != null && note.trim().isNotEmpty) 'note': note.trim(),
    });
    if (!result.isSuccess) return ApiResult.failure(result.error ?? 'Site power command failed');
    return ApiResult.success(ControlCommandResult.fromJson(result.data ?? {}));
  }

  ApiResult<List<AssetSummary>> _parseAssetList(Map<String, dynamic> data) {
    final rawAssets = data['assets'] ?? data['items'] ?? data['data'];
    if (rawAssets is List) {
      return ApiResult.success(rawAssets.whereType<Map>().map((item) => AssetSummary.fromJson(Map<String, dynamic>.from(item))).toList());
    }
    if (rawAssets is Map) {
      return ApiResult.success(rawAssets.entries.where((entry) => entry.value is Map).map((entry) {
        final item = Map<String, dynamic>.from(entry.value as Map);
        item.putIfAbsent('asset_id', () => entry.key.toString());
        return AssetSummary.fromJson(item);
      }).toList());
    }
    return ApiResult.failure('Invalid asset response: expected assets/items list or map, got ${rawAssets.runtimeType}');
  }

  ApiResult<List<SourceSummary>> _parseSourceList(Map<String, dynamic> data) {
    final rawSources = data['items'] ?? data['sources'] ?? data['data'];
    if (rawSources is List) {
      return ApiResult.success(rawSources.whereType<Map>().map((item) => SourceSummary.fromJson(Map<String, dynamic>.from(item))).toList());
    }
    return const ApiResult.success([]);
  }

  Future<ApiResult<Map<String, dynamic>>> _postJson(String path, Map<String, dynamic> body) async {
    try {
      final uri = _uri(path);
      final response = await http.post(uri, headers: _jsonHeaders(), body: jsonEncode(body)).timeout(httpTimeout);
      if (response.statusCode == 401) {
        onUnauthorized?.call();
        return ApiResult.failure('Unauthorized. Please login again.');
      }
      if (response.statusCode == 403) return ApiResult.failure('Forbidden for current login role.');
      if (response.statusCode < 200 || response.statusCode >= 300) {
        return ApiResult.failure('HTTP ${response.statusCode}: ${response.body}');
      }
      final decoded = jsonDecode(response.body);
      if (decoded is! Map) return const ApiResult.failure('Response is not a JSON object');
      return ApiResult.success(Map<String, dynamic>.from(decoded));
    } catch (e) {
      return ApiResult.failure('Request failed after ${httpTimeout.inSeconds}s: $e');
    }
  }

  Future<ApiResult<Map<String, dynamic>>> _getJson(String path, [Map<String, String>? query]) async {
    try {
      final uri = _uri(path, query);
      final response = await http.get(uri, headers: _headers()).timeout(httpTimeout);
      if (response.statusCode == 401) {
        onUnauthorized?.call();
        return ApiResult.failure('Unauthorized. Please login again.');
      }
      if (response.statusCode == 403) {
        return ApiResult.failure('Forbidden for current login role.');
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        return ApiResult.failure('HTTP ${response.statusCode}: ${response.body}');
      }
      final decoded = jsonDecode(response.body);
      if (decoded is! Map) return const ApiResult.failure('Response is not a JSON object');
      return ApiResult.success(Map<String, dynamic>.from(decoded));
    } catch (e) {
      return ApiResult.failure('Request failed after ${httpTimeout.inSeconds}s: $e');
    }
  }
}
