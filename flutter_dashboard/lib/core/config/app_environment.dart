import 'network_config.dart';

/// App-level environment settings.
///
/// Later this can be loaded from a settings screen, JSON asset, flavor, or
/// command-line define. For now it keeps the current hardware defaults stable.
class AppEnvironment {
  final String gatewayId;
  final String chillerAssetId;
  final String pcsAssetId;
  final String bmsAssetId;
  final NetworkConfig network;

  const AppEnvironment({
    required this.gatewayId,
    required this.chillerAssetId,
    required this.pcsAssetId,
    required this.bmsAssetId,
    required this.network,
  });

  factory AppEnvironment.hardware({
    String ethHost = '192.168.10.2',
    String? restHost,
    String? logHost,
  }) {
    return AppEnvironment(
      gatewayId: 'imx93_gateway_1',
      chillerAssetId: 'chiller_1',
      pcsAssetId: 'pcs_1',
      bmsAssetId: 'bms_1',
      network: NetworkConfig.hardware(
        ethHost: ethHost,
        restHost: restHost,
        logHost: logHost,
      ),
    );
  }

  List<String> get supportedAssetIds => [
        chillerAssetId,
        pcsAssetId,
        bmsAssetId,
      ];
}
