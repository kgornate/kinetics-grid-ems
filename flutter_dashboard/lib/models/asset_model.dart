import '../core/utils/json_utils.dart';

/// Runtime asset record returned by the backend `/api/assets` endpoint.
class AssetModel {
  final String assetId;
  final String assetKey;
  final String assetType;
  final bool enabled;
  final bool running;
  final bool online;
  final String? protocol;
  final String? profile;
  final String? vendor;
  final bool configured;
  final bool telemetryAvailable;
  final String runtimeMode;
  final Map<String, dynamic> compatibility;
  final Map<String, dynamic> connection;
  final Map<String, dynamic> metadata;
  final Map<String, dynamic> raw;

  const AssetModel({
    required this.assetId,
    required this.assetKey,
    required this.assetType,
    required this.enabled,
    required this.running,
    required this.online,
    required this.protocol,
    required this.profile,
    required this.vendor,
    required this.configured,
    required this.telemetryAvailable,
    required this.runtimeMode,
    required this.compatibility,
    required this.connection,
    required this.metadata,
    required this.raw,
  });

  factory AssetModel.fromJson(Map<String, dynamic> json) {
    return AssetModel(
      assetId: JsonUtils.asString(json['asset_id']) ?? '',
      assetKey: JsonUtils.asString(json['asset_key']) ?? '',
      assetType: JsonUtils.asString(json['asset_type']) ?? '',
      enabled: JsonUtils.asBool(json['enabled']) ?? false,
      running: JsonUtils.asBool(json['running']) ?? false,
      online: JsonUtils.asBool(json['online']) ?? false,
      protocol: JsonUtils.asString(json['protocol']),
      profile: JsonUtils.asString(json['profile']),
      vendor: JsonUtils.asString(json['vendor']),
      configured: JsonUtils.asBool(json['configured']) ?? false,
      telemetryAvailable: JsonUtils.asBool(json['telemetry_available']) ?? false,
      runtimeMode: JsonUtils.asString(json['runtime_mode']) ?? 'unknown',
      compatibility: JsonUtils.asMap(json['compatibility']),
      connection: JsonUtils.asMap(json['connection']),
      metadata: JsonUtils.asMap(json['metadata']),
      raw: Map<String, dynamic>.from(json),
    );
  }

  bool get isActiveService => runtimeMode == 'active_service';
  bool get isConfiguredOnly => runtimeMode == 'configured_only';
  bool get isConfiguredFuture => runtimeMode == 'configured_future';
  bool get isDisabled => runtimeMode == 'disabled' || !enabled;

  Map<String, dynamic> toJson() => Map<String, dynamic>.from(raw);
}

class AssetListResponse {
  final String status;
  final String? gatewayId;
  final String? timestamp;
  final int assetsCount;
  final List<AssetModel> assets;
  final Map<String, dynamic> summary;
  final Map<String, dynamic> raw;

  const AssetListResponse({
    required this.status,
    required this.gatewayId,
    required this.timestamp,
    required this.assetsCount,
    required this.assets,
    required this.summary,
    required this.raw,
  });

  factory AssetListResponse.fromJson(Map<String, dynamic> json) {
    final list = JsonUtils.asList(json['assets']);
    return AssetListResponse(
      status: JsonUtils.asString(json['status']) ?? 'unknown',
      gatewayId: JsonUtils.asString(json['gateway_id']),
      timestamp: JsonUtils.asString(json['timestamp']),
      assetsCount: JsonUtils.asInt(json['assets_count']) ?? list.length,
      assets: list
          .whereType<Map>()
          .map((item) => AssetModel.fromJson(Map<String, dynamic>.from(item)))
          .toList(growable: false),
      summary: JsonUtils.asMap(json['summary']),
      raw: Map<String, dynamic>.from(json),
    );
  }

  AssetModel? findById(String assetId) {
    final target = assetId.toLowerCase();
    for (final asset in assets) {
      if (asset.assetId.toLowerCase() == target ||
          asset.assetKey.toLowerCase() == target) {
        return asset;
      }
    }
    return null;
  }
}

class AssetResponse {
  final String status;
  final AssetModel? asset;
  final String? timestamp;
  final Map<String, dynamic> raw;

  const AssetResponse({
    required this.status,
    required this.asset,
    required this.timestamp,
    required this.raw,
  });

  factory AssetResponse.fromJson(Map<String, dynamic> json) {
    final assetMap = JsonUtils.asMap(json['asset']);
    return AssetResponse(
      status: JsonUtils.asString(json['status']) ?? 'unknown',
      asset: assetMap.isEmpty ? null : AssetModel.fromJson(assetMap),
      timestamp: JsonUtils.asString(json['timestamp']),
      raw: Map<String, dynamic>.from(json),
    );
  }
}
