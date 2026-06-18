import '../core/utils/json_utils.dart';

class GatewayStatusModel {
  final String? gatewayId;
  final String? mode;
  final Map<String, dynamic> network;
  final Map<String, dynamic> chiller;
  final Map<String, dynamic> pcs;
  final Map<String, dynamic> bms;
  final Map<String, dynamic> runtimeConfig;
  final Map<String, dynamic> raw;

  const GatewayStatusModel({
    required this.gatewayId,
    required this.mode,
    required this.network,
    required this.chiller,
    required this.pcs,
    required this.bms,
    required this.runtimeConfig,
    required this.raw,
  });

  factory GatewayStatusModel.fromJson(Map<String, dynamic> json) {
    return GatewayStatusModel(
      gatewayId: JsonUtils.asString(json['gateway_id']),
      mode: JsonUtils.asString(json['mode']),
      network: JsonUtils.asMap(json['network']),
      chiller: JsonUtils.asMap(json['chiller']),
      pcs: JsonUtils.asMap(json['pcs']),
      bms: JsonUtils.asMap(json['bms']),
      runtimeConfig: JsonUtils.asMap(json['runtime_config']),
      raw: Map<String, dynamic>.from(json),
    );
  }
}
