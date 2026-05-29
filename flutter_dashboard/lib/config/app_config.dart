class AppConfig {
  static const String defaultGatewayIp = '192.168.10.2';

  static const int tcpCommandPort = 6000;
  static const int udpTelemetryPort = 5005;

  static const int logHttpPort = 7000;

  static const Duration tcpTimeout = Duration(seconds: 5);
  static const Duration httpTimeout = Duration(seconds: 8);

  static const String gatewayId = 'imx93_gateway_1';

  static const String chillerAssetId = 'chiller_1';
  static const String pcsAssetId = 'pcs_1';

  static const List<String> supportedLogAssets = [
    chillerAssetId,
    pcsAssetId,
  ];

  static const List<String> supportedPcsVendors = [
    'njoy',
    'inpower',
  ];

  // Kept for backward compatibility with existing chiller code.
  static const String assetId = chillerAssetId;

  static String logApiBaseUrl(String gatewayIp) {
    return 'http://$gatewayIp:$logHttpPort';
  }
}
