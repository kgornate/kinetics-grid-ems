import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/alarm_record.dart';
import '../models/api_result.dart';
import '../models/asset_summary.dart';

class NorthboundApiClient {
  NorthboundApiClient({required this.baseUrl});

  final String baseUrl;

  Uri _uri(String path, [Map<String, String>? query]) {
    final cleanBase = baseUrl.endsWith('/') ? baseUrl.substring(0, baseUrl.length - 1) : baseUrl;
    return Uri.parse('$cleanBase$path').replace(queryParameters: query);
  }

  Future<ApiResult<Map<String, dynamic>>> getHealth() async {
    return _getJson('/api/health');
  }

  Future<ApiResult<List<AssetSummary>>> getAssets() async {
    final result = await _getJson('/api/assets');
    if (!result.isSuccess) return ApiResult.failure(result.error ?? 'Failed to read assets');
    final data = result.data ?? {};
    final rawAssets = data['assets'];

    if (rawAssets is List) {
      return ApiResult.success(
        rawAssets
            .whereType<Map>()
            .map((item) => AssetSummary.fromJson(Map<String, dynamic>.from(item)))
            .toList(),
      );
    }

    if (rawAssets is Map) {
      return ApiResult.success(
        rawAssets.entries
            .where((entry) => entry.value is Map)
            .map((entry) {
              final item = Map<String, dynamic>.from(entry.value as Map);
              item.putIfAbsent('asset_id', () => entry.key.toString());
              return AssetSummary.fromJson(item);
            })
            .toList(),
      );
    }

    return const ApiResult.failure('Invalid /api/assets response: assets must be a list or map');
  }

  Future<ApiResult<Map<String, dynamic>>> getKeySignals() async {
    return _getJson('/api/telemetry/key-signals');
  }

  Future<ApiResult<Map<String, dynamic>>> getAssetTelemetry(String assetId, {String? category}) async {
    final query = category == null || category.isEmpty ? null : {'category': category};
    return _getJson('/api/assets/$assetId/telemetry', query);
  }

  Future<ApiResult<Map<String, dynamic>>> getAssetKeySignals(String assetId) async {
    return _getJson('/api/assets/$assetId/key-signals');
  }

  Future<ApiResult<List<AlarmRecord>>> getAlarms() async {
    final result = await _getJson('/api/alarms');
    if (!result.isSuccess) return ApiResult.failure(result.error ?? 'Failed to read alarms');
    final data = result.data ?? {};
    final rawAlarms = data['alarms'];
    if (rawAlarms is! List) return const ApiResult.failure('Invalid /api/alarms response: alarms is not a list');
    return ApiResult.success(
      rawAlarms
          .whereType<Map>()
          .map((item) => AlarmRecord.fromJson(Map<String, dynamic>.from(item)))
          .toList(),
    );
  }

  Future<ApiResult<Map<String, dynamic>>> getStorageStatus() async {
    return _getJson('/api/storage/status');
  }

  Future<ApiResult<Map<String, dynamic>>> getRegisterMap() async {
    return _getJson('/api/registers/map');
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
