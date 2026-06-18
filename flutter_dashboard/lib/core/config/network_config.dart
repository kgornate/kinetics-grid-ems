/// Network configuration for the EMS dashboard.
///
/// This class centralizes gateway IPs, ports, and endpoint base URLs so UI
/// widgets and feature services do not hardcode connection details.
class NetworkConfig {
  final String gatewayRestHost;
  final int gatewayRestPort;
  final String gatewayTcpHost;
  final int gatewayTcpPort;
  final String logApiHost;
  final int logApiPort;
  final int udpTelemetryPort;
  final Duration tcpTimeout;
  final Duration httpTimeout;

  const NetworkConfig({
    required this.gatewayRestHost,
    required this.gatewayRestPort,
    required this.gatewayTcpHost,
    required this.gatewayTcpPort,
    required this.logApiHost,
    required this.logApiPort,
    required this.udpTelemetryPort,
    this.tcpTimeout = const Duration(seconds: 5),
    this.httpTimeout = const Duration(seconds: 8),
  });

  /// Current default hardware setup.
  ///
  /// eth0 is typically used by Flutter/TCP/UDP on the PC side.
  /// mlan0/Wi-Fi can be used for REST/Web API if the dashboard runs over Wi-Fi.
  factory NetworkConfig.hardware({
    String ethHost = '192.168.10.2',
    String? restHost,
    String? logHost,
  }) {
    final resolvedRestHost = restHost ?? ethHost;
    final resolvedLogHost = logHost ?? ethHost;
    return NetworkConfig(
      gatewayRestHost: resolvedRestHost,
      gatewayRestPort: 8000,
      gatewayTcpHost: ethHost,
      gatewayTcpPort: 6000,
      logApiHost: resolvedLogHost,
      logApiPort: 7000,
      udpTelemetryPort: 5005,
    );
  }

  factory NetworkConfig.localhost() {
    return const NetworkConfig(
      gatewayRestHost: '127.0.0.1',
      gatewayRestPort: 8000,
      gatewayTcpHost: '127.0.0.1',
      gatewayTcpPort: 6000,
      logApiHost: '127.0.0.1',
      logApiPort: 7000,
      udpTelemetryPort: 5005,
    );
  }

  Uri gatewayUri(
    String path, {
    Map<String, String>? queryParameters,
  }) {
    return Uri(
      scheme: 'http',
      host: gatewayRestHost,
      port: gatewayRestPort,
      path: path,
      queryParameters: queryParameters,
    );
  }

  Uri logUri(
    String path, {
    Map<String, String>? queryParameters,
  }) {
    return Uri(
      scheme: 'http',
      host: logApiHost,
      port: logApiPort,
      path: path,
      queryParameters: queryParameters,
    );
  }

  String get gatewayBaseUrl => 'http://$gatewayRestHost:$gatewayRestPort';
  String get logApiBaseUrl => 'http://$logApiHost:$logApiPort';
}
