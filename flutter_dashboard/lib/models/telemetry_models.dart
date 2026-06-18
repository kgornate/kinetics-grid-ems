import '../core/utils/json_utils.dart';

/// Full/operator telemetry packet returned by backend telemetry endpoints.
class TelemetryEnvelope {
  final String status;
  final String? type;
  final String? view;
  final String? gatewayId;
  final String? assetId;
  final String? assetType;
  final String? assetKey;
  final String? timestamp;
  final bool? online;
  final String? runtimeMode;
  final Map<String, dynamic> data;
  final Map<String, dynamic> telemetry;
  final Map<String, dynamic> pcs;
  final Map<String, dynamic> bms;
  final Map<String, dynamic> chiller;
  final Map<String, dynamic> assets;
  final Map<String, dynamic> raw;

  const TelemetryEnvelope({
    required this.status,
    required this.type,
    required this.view,
    required this.gatewayId,
    required this.assetId,
    required this.assetType,
    required this.assetKey,
    required this.timestamp,
    required this.online,
    required this.runtimeMode,
    required this.data,
    required this.telemetry,
    required this.pcs,
    required this.bms,
    required this.chiller,
    required this.assets,
    required this.raw,
  });

  factory TelemetryEnvelope.fromJson(Map<String, dynamic> json) {
    final telemetry = JsonUtils.asMap(json['telemetry']);
    final data = JsonUtils.asMap(json['data']);
    final assets = JsonUtils.asMap(json['assets']);
    final assetId = JsonUtils.asString(json['asset_id']);
    return TelemetryEnvelope(
      status: JsonUtils.asString(json['status']) ?? 'ok',
      type: JsonUtils.asString(json['type']),
      view: JsonUtils.asString(json['view']),
      gatewayId: JsonUtils.asString(json['gateway_id']),
      assetId: assetId,
      assetType: JsonUtils.asString(json['asset_type']),
      assetKey: JsonUtils.asString(json['asset_key']),
      timestamp: JsonUtils.asString(json['timestamp']),
      online: JsonUtils.asBool(json['online']),
      runtimeMode: JsonUtils.asString(json['runtime_mode']),
      data: data,
      telemetry: telemetry,
      pcs: JsonUtils.asMap(json['pcs'] ?? assets['pcs']),
      bms: JsonUtils.asMap(json['bms'] ?? assets['bms']),
      chiller: _extractChiller(json, assets, data, assetId),
      assets: assets,
      raw: Map<String, dynamic>.from(json),
    );
  }

  static Map<String, dynamic> _extractChiller(
    Map<String, dynamic> json,
    Map<String, dynamic> assets,
    Map<String, dynamic> data,
    String? assetId,
  ) {
    final direct = JsonUtils.asMap(json['chiller'] ?? assets['chiller']);
    if (direct.isNotEmpty) return direct;
    if ((assetId == 'chiller' || assetId == 'chiller_1') && data.isNotEmpty) {
      return data;
    }
    return <String, dynamic>{};
  }

  bool get isOperatorView => view == 'operator';

  Map<String, dynamic> telemetryForAsset(String assetId) {
    final key = assetId.toLowerCase();
    if (key == 'pcs' || key == 'pcs_1') return pcs;
    if (key == 'bms' || key == 'bms_1') return bms;
    if (key == 'chiller' || key == 'chiller_1') return chiller;
    return JsonUtils.asMap(assets[key]);
  }
}

class AssetTelemetryResponse {
  final String status;
  final String assetId;
  final String assetType;
  final String assetKey;
  final String? timestamp;
  final bool online;
  final String? runtimeMode;
  final Map<String, dynamic> telemetry;
  final Map<String, dynamic> raw;

  const AssetTelemetryResponse({
    required this.status,
    required this.assetId,
    required this.assetType,
    required this.assetKey,
    required this.timestamp,
    required this.online,
    required this.runtimeMode,
    required this.telemetry,
    required this.raw,
  });

  factory AssetTelemetryResponse.fromJson(Map<String, dynamic> json) {
    return AssetTelemetryResponse(
      status: JsonUtils.asString(json['status']) ?? 'unknown',
      assetId: JsonUtils.asString(json['asset_id']) ?? '',
      assetType: JsonUtils.asString(json['asset_type']) ?? '',
      assetKey: JsonUtils.asString(json['asset_key']) ?? '',
      timestamp: JsonUtils.asString(json['timestamp']),
      online: JsonUtils.asBool(json['online']) ?? false,
      runtimeMode: JsonUtils.asString(json['runtime_mode']),
      telemetry: JsonUtils.asMap(json['telemetry']),
      raw: Map<String, dynamic>.from(json),
    );
  }
}
