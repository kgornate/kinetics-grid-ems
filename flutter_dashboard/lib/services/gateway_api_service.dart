import '../config/app_config.dart';
import '../core/api/api_client.dart';
import '../core/api/endpoint_paths.dart';
import '../core/api/query_utils.dart';
import '../models/models.dart';

/// REST client for the EMS gateway Web API on port 8000.
///
/// This service is additive. Existing screens can keep using UDP/TCP for now,
/// while new screens can gradually move to the stable REST endpoints exposed by
/// the backend.
class GatewayApiService {
  final String gatewayIp;
  final int port;
  final Duration timeout;
  late final ApiClient _client = ApiClient(
    host: gatewayIp,
    port: port,
    timeout: timeout,
  );

  GatewayApiService({
    required this.gatewayIp,
    this.port = AppConfig.webApiPort,
    this.timeout = AppConfig.httpTimeout,
  });

  Future<Map<String, dynamic>> fetchGatewayHealth() {
    return _client.getJson(EndpointPaths.gatewayHealth);
  }

  Future<Map<String, dynamic>> fetchGatewayStatus() {
    return _client.getJson(EndpointPaths.gatewayStatus);
  }

  Future<Map<String, dynamic>> fetchAssets() {
    return _client.getJson(EndpointPaths.assets);
  }

  Future<Map<String, dynamic>> fetchAsset(String assetId) {
    return _client.getJson(EndpointPaths.asset(assetId));
  }

  Future<AssetListResponse> fetchAssetsTyped() async {
    final json = await fetchAssets();
    return AssetListResponse.fromJson(json);
  }

  Future<AssetResponse> fetchAssetTyped(String assetId) async {
    final json = await fetchAsset(assetId);
    return AssetResponse.fromJson(json);
  }

  Future<Map<String, dynamic>> fetchLatestTelemetry({
    bool operatorView = false,
  }) {
    return _client.getJson(
      operatorView ? EndpointPaths.telemetryOperator : EndpointPaths.telemetryLatest,
    );
  }

  Future<Map<String, dynamic>> fetchAssetTelemetry({
    required String assetId,
    bool operatorView = false,
  }) {
    return _client.getJson(
      operatorView
          ? EndpointPaths.assetTelemetryOperator(assetId)
          : EndpointPaths.assetTelemetryLatest(assetId),
    );
  }

  Future<TelemetryEnvelope> fetchLatestTelemetryTyped({
    bool operatorView = false,
  }) async {
    final json = await fetchLatestTelemetry(operatorView: operatorView);
    return TelemetryEnvelope.fromJson(json);
  }

  Future<AssetTelemetryResponse> fetchAssetTelemetryTyped({
    required String assetId,
    bool operatorView = false,
  }) async {
    final json = await fetchAssetTelemetry(
      assetId: assetId,
      operatorView: operatorView,
    );
    return AssetTelemetryResponse.fromJson(json);
  }

  Future<Map<String, dynamic>> fetchHealth() {
    return _client.getJson(EndpointPaths.health);
  }

  Future<Map<String, dynamic>> fetchGatewayHealthDetails() {
    return _client.getJson(EndpointPaths.healthGateway);
  }

  Future<Map<String, dynamic>> fetchAssetsHealth() {
    return _client.getJson(EndpointPaths.healthAssets);
  }

  Future<Map<String, dynamic>> fetchAssetHealth(String assetId) {
    return _client.getJson(EndpointPaths.assetHealth(assetId));
  }

  Future<Map<String, dynamic>> fetchDiagnostics() {
    return _client.getJson(EndpointPaths.diagnostics);
  }

  Future<Map<String, dynamic>> fetchAssetDiagnostics(String assetId) {
    return _client.getJson(EndpointPaths.assetDiagnostics(assetId));
  }

  Future<GatewayHealthModel> fetchHealthTyped() async {
    final json = await fetchHealth();
    return GatewayHealthModel.fromJson(json);
  }

  Future<GatewayHealthModel> fetchGatewayHealthDetailsTyped() async {
    final json = await fetchGatewayHealthDetails();
    return GatewayHealthModel.fromJson(json);
  }

  Future<AssetsHealthResponse> fetchAssetsHealthTyped() async {
    final json = await fetchAssetsHealth();
    return AssetsHealthResponse.fromJson(json);
  }

  Future<AssetHealthModel> fetchAssetHealthTyped(String assetId) async {
    final json = await fetchAssetHealth(assetId);
    return AssetHealthModel.fromJson(json);
  }

  Future<DiagnosticsResponse> fetchDiagnosticsTyped() async {
    final json = await fetchDiagnostics();
    return DiagnosticsResponse.fromJson(json);
  }

  Future<AssetDiagnosticsResponse> fetchAssetDiagnosticsTyped(String assetId) async {
    final json = await fetchAssetDiagnostics(assetId);
    return AssetDiagnosticsResponse.fromJson(json);
  }

  Uri buildUri(
    String path, {
    Map<String, String?> query = const {},
  }) {
    return _client.uri(
      path,
      queryParameters: QueryUtils.clean(query),
    );
  }
}
