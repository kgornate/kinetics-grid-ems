class AppConfig {
  static const String defaultGatewayIp = '10.55.202.131';

  static const int tcpCommandPort = 6000;
  static const int udpTelemetryPort = 5005;

  static const Duration tcpTimeout = Duration(seconds: 5);

  static const String gatewayId = 'imx93_gateway_1';
  static const String assetId = 'chiller_1';
}