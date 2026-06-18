import '../core/utils/json_utils.dart';

class AssetHealthModel {
  final String status;
  final String assetId;
  final String assetKey;
  final String assetType;
  final bool enabled;
  final bool running;
  final bool online;
  final String? runtimeMode;
  final String? protocol;
  final String? profile;
  final String? vendor;
  final Map<String, dynamic> connection;
  final String? lastSuccessfulPoll;
  final String? lastError;
  final int consecutiveFailures;
  final String? reason;
  final String? recommendedAction;
  final Map<String, dynamic> storage;
  final String? timestamp;
  final Map<String, dynamic> raw;

  const AssetHealthModel({
    required this.status,
    required this.assetId,
    required this.assetKey,
    required this.assetType,
    required this.enabled,
    required this.running,
    required this.online,
    required this.runtimeMode,
    required this.protocol,
    required this.profile,
    required this.vendor,
    required this.connection,
    required this.lastSuccessfulPoll,
    required this.lastError,
    required this.consecutiveFailures,
    required this.reason,
    required this.recommendedAction,
    required this.storage,
    required this.timestamp,
    required this.raw,
  });

  factory AssetHealthModel.fromJson(Map<String, dynamic> json) {
    return AssetHealthModel(
      status: JsonUtils.asString(json['status']) ?? 'unknown',
      assetId: JsonUtils.asString(json['asset_id']) ?? '',
      assetKey: JsonUtils.asString(json['asset_key']) ?? '',
      assetType: JsonUtils.asString(json['asset_type']) ?? '',
      enabled: JsonUtils.asBool(json['enabled']) ?? false,
      running: JsonUtils.asBool(json['running']) ?? false,
      online: JsonUtils.asBool(json['online']) ?? false,
      runtimeMode: JsonUtils.asString(json['runtime_mode']),
      protocol: JsonUtils.asString(json['protocol']),
      profile: JsonUtils.asString(json['profile']),
      vendor: JsonUtils.asString(json['vendor']),
      connection: JsonUtils.asMap(json['connection']),
      lastSuccessfulPoll: JsonUtils.asString(json['last_successful_poll']),
      lastError: JsonUtils.asString(json['last_error']),
      consecutiveFailures: JsonUtils.asInt(json['consecutive_failures']) ?? 0,
      reason: JsonUtils.asString(json['reason']),
      recommendedAction: JsonUtils.asString(json['recommended_action']),
      storage: JsonUtils.asMap(json['storage']),
      timestamp: JsonUtils.asString(json['timestamp']),
      raw: Map<String, dynamic>.from(json),
    );
  }

  bool get isHealthy => status == 'healthy';
  bool get isDegraded => status == 'degraded';
  bool get isOffline => status == 'offline';
  bool get isDisabled => status == 'disabled';
}

class AssetsHealthResponse {
  final String status;
  final String? timestamp;
  final Map<String, dynamic> summary;
  final Map<String, AssetHealthModel> assets;
  final Map<String, dynamic> raw;

  const AssetsHealthResponse({
    required this.status,
    required this.timestamp,
    required this.summary,
    required this.assets,
    required this.raw,
  });

  factory AssetsHealthResponse.fromJson(Map<String, dynamic> json) {
    final rawAssets = JsonUtils.asMap(json['assets']);
    final parsedAssets = <String, AssetHealthModel>{};
    for (final entry in rawAssets.entries) {
      final value = JsonUtils.asMap(entry.value);
      if (value.isNotEmpty) {
        parsedAssets[entry.key] = AssetHealthModel.fromJson(value);
      }
    }
    return AssetsHealthResponse(
      status: JsonUtils.asString(json['status']) ?? 'unknown',
      timestamp: JsonUtils.asString(json['timestamp']),
      summary: JsonUtils.asMap(json['summary']),
      assets: parsedAssets,
      raw: Map<String, dynamic>.from(json),
    );
  }
}

class GatewayHealthModel {
  final String status;
  final String? gatewayId;
  final String? timestamp;
  final String? mode;
  final Map<String, dynamic> summary;
  final Map<String, dynamic> services;
  final String? recommendedAction;
  final Map<String, AssetHealthModel> assets;
  final Map<String, dynamic> raw;

  const GatewayHealthModel({
    required this.status,
    required this.gatewayId,
    required this.timestamp,
    required this.mode,
    required this.summary,
    required this.services,
    required this.recommendedAction,
    required this.assets,
    required this.raw,
  });

  factory GatewayHealthModel.fromJson(Map<String, dynamic> json) {
    final assetsMap = JsonUtils.asMap(json['assets']);
    final assets = <String, AssetHealthModel>{};
    for (final entry in assetsMap.entries) {
      final value = JsonUtils.asMap(entry.value);
      if (value.isNotEmpty) {
        assets[entry.key] = AssetHealthModel.fromJson(value);
      }
    }

    final gateway = JsonUtils.asMap(json['gateway']);
    return GatewayHealthModel(
      status: JsonUtils.asString(json['status']) ?? 'unknown',
      gatewayId: JsonUtils.asString(json['gateway_id'] ?? gateway['gateway_id']),
      timestamp: JsonUtils.asString(json['timestamp'] ?? gateway['timestamp']),
      mode: JsonUtils.asString(json['mode'] ?? gateway['mode']),
      summary: JsonUtils.asMap(json['summary'] ?? gateway['summary']),
      services: JsonUtils.asMap(json['services'] ?? gateway['services']),
      recommendedAction: JsonUtils.asString(
        json['recommended_action'] ?? gateway['recommended_action'],
      ),
      assets: assets,
      raw: Map<String, dynamic>.from(json),
    );
  }
}
