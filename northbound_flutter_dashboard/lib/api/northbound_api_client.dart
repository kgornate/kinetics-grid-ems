import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/alarm_record.dart';
import '../models/api_result.dart';
import '../models/asset_summary.dart';
import '../models/log_filter_options.dart';
import '../models/log_record.dart';
import '../models/storage_status.dart';

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
  NorthboundApiClient({required this.baseUrl});

  final String baseUrl;

  Uri _uri(String path, [Map<String, String>? query]) {
    final cleanBase = baseUrl.endsWith('/') ? baseUrl.substring(0, baseUrl.length - 1) : baseUrl;
    return Uri.parse('$cleanBase$path').replace(queryParameters: query);
  }

  String urlFor(String path, [Map<String, String>? query]) => _uri(path, query).toString();

  Future<ApiResult<Map<String, dynamic>>> getHealth() async => _getJson('/api/health');

  Future<ApiResult<List<AssetSummary>>> getAssets() async {
    final result = await _getJson('/api/assets');
    if (!result.isSuccess) return ApiResult.failure(result.error ?? 'Failed to read assets');
    final data = result.data ?? {};
    final rawAssets = data['assets'];

    if (rawAssets is List) {
      return ApiResult.success(
        rawAssets.whereType<Map>().map((item) => AssetSummary.fromJson(Map<String, dynamic>.from(item))).toList(),
      );
    }

    if (rawAssets is Map) {
      return ApiResult.success(
        rawAssets.entries.where((entry) => entry.value is Map).map((entry) {
          final item = Map<String, dynamic>.from(entry.value as Map);
          item.putIfAbsent('asset_id', () => entry.key.toString());
          return AssetSummary.fromJson(item);
        }).toList(),
      );
    }

    return const ApiResult.failure('Invalid /api/assets response: assets must be a list or map');
  }

  Future<ApiResult<Map<String, dynamic>>> getKeySignals() async => _getJson('/api/telemetry/key-signals');

  Future<ApiResult<Map<String, dynamic>>> getAssetTelemetry(String assetId, {String? category}) async {
    final query = category == null || category.isEmpty ? null : {'category': category};
    return _getJson('/api/assets/$assetId/telemetry', query);
  }

  Future<ApiResult<List<AlarmRecord>>> getAlarms() async {
    final result = await _getJson('/api/alarms');
    if (!result.isSuccess) return ApiResult.failure(result.error ?? 'Failed to read alarms');
    final data = result.data ?? {};
    final rawAlarms = data['alarms'];
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

  Future<ApiResult<Map<String, dynamic>>> getSnapshots({String? assetId, int limit = 20}) async {
    final query = <String, String>{'limit': limit.toString()};
    if (assetId != null && assetId.trim().isNotEmpty) query['asset_id'] = assetId.trim();
    return _getJson('/api/storage/snapshots', query);
  }

  Future<ApiResult<Map<String, dynamic>>> getPoints({required String assetId, required String signalName, int limit = 100}) async {
    return _getJson('/api/storage/points', {'asset_id': assetId, 'signal_name': signalName, 'limit': limit.toString()});
  }

  Future<ApiResult<Map<String, dynamic>>> _getJson(String path, [Map<String, String>? query]) async {
    try {
      final response = await http.get(_uri(path, query)).timeout(const Duration(seconds: 5));
      if (response.statusCode < 200 || response.statusCode >= 300) {
        return ApiResult.failure('HTTP ${response.statusCode}: ${response.body}');
      }
      final decoded = jsonDecode(response.body);
      if (decoded is! Map) return const ApiResult.failure('Response is not a JSON object');
      return ApiResult.success(Map<String, dynamic>.from(decoded));
    } catch (e) {
      return ApiResult.failure(e.toString());
    }
  }
}
