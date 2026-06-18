/// Backend endpoint constants aligned with the stable EMS gateway baseline.
class EndpointPaths {
  EndpointPaths._();

  static const String gatewayHealth = '/api/gateway/health';
  static const String gatewayStatus = '/api/gateway/status';
  static const String assets = '/api/assets';
  static const String telemetryLatest = '/api/telemetry/latest';
  static const String telemetryOperator = '/api/telemetry/operator';
  static const String health = '/api/health';
  static const String healthGateway = '/api/health/gateway';
  static const String healthAssets = '/api/health/assets';
  static const String diagnostics = '/api/diagnostics';

  static const String logHealth = '/api/health';
  static const String logAssets = '/api/logs/assets';
  static const String logFiles = '/api/logs/files';
  static const String logTelemetry = '/api/logs/telemetry';
  static const String logEvents = '/api/logs/events';
  static const String logErrors = '/api/logs/errors';
  static const String logMetadata = '/api/logs/metadata';
  static const String storageStatus = '/api/storage/status';
  static const String storageHealth = '/api/storage/health';
  static const String telemetryCsvDownload = '/api/logs/download/telemetry';

  static String asset(String assetId) => '/api/assets/$assetId';
  static String assetTelemetryLatest(String assetId) =>
      '/api/assets/$assetId/telemetry/latest';
  static String assetTelemetryOperator(String assetId) =>
      '/api/assets/$assetId/telemetry/operator';
  static String assetHealth(String assetId) => '/api/health/assets/$assetId';
  static String assetDiagnostics(String assetId) =>
      '/api/diagnostics/assets/$assetId';
}
