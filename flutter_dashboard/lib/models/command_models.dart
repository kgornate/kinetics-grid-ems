import '../core/utils/json_utils.dart';

class GatewayCommandRequest {
  final String command;
  final String requestId;
  final String? assetId;
  final dynamic value;
  final Map<String, dynamic> params;

  const GatewayCommandRequest({
    required this.command,
    required this.requestId,
    this.assetId,
    this.value,
    this.params = const <String, dynamic>{},
  });

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{
      'command': command,
      'request_id': requestId,
    };
    if (assetId != null) json['asset_id'] = assetId;
    if (value != null) json['value'] = value;
    json.addAll(params);
    return json;
  }
}

class GatewayCommandResponse {
  final String status;
  final String? command;
  final String? requestId;
  final String? assetId;
  final String? message;
  final Map<String, dynamic> data;
  final Map<String, dynamic> raw;

  const GatewayCommandResponse({
    required this.status,
    required this.command,
    required this.requestId,
    required this.assetId,
    required this.message,
    required this.data,
    required this.raw,
  });

  factory GatewayCommandResponse.fromJson(Map<String, dynamic> json) {
    return GatewayCommandResponse(
      status: JsonUtils.asString(json['status']) ?? 'unknown',
      command: JsonUtils.asString(json['command']),
      requestId: JsonUtils.asString(json['request_id']),
      assetId: JsonUtils.asString(json['asset_id']),
      message: JsonUtils.asString(json['message']),
      data: JsonUtils.asMap(json['data']),
      raw: Map<String, dynamic>.from(json),
    );
  }

  bool get isOk => status.toLowerCase() == 'ok' || status.toLowerCase() == 'success';
}
