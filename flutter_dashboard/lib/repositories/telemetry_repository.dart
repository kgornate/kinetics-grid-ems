import '../models/models.dart';
import '../services/gateway_api_service.dart';
import 'repository_exception.dart';

/// Repository for full and operator telemetry APIs.
class TelemetryRepository {
  final GatewayApiService api;

  const TelemetryRepository({required this.api});

  factory TelemetryRepository.forGateway(String gatewayIp) {
    return TelemetryRepository(api: GatewayApiService(gatewayIp: gatewayIp));
  }

  Future<TelemetryEnvelope> fetchLatest({bool operatorView = false}) async {
    try {
      return await api.fetchLatestTelemetryTyped(operatorView: operatorView);
    } catch (error) {
      throw RepositoryException('Failed to fetch latest telemetry', cause: error);
    }
  }

  Future<TelemetryEnvelope> fetchOperatorTelemetry() {
    return fetchLatest(operatorView: true);
  }

  Future<AssetTelemetryResponse> fetchAssetTelemetry(
    String assetId, {
    bool operatorView = false,
  }) async {
    try {
      return await api.fetchAssetTelemetryTyped(
        assetId: assetId,
        operatorView: operatorView,
      );
    } catch (error) {
      throw RepositoryException('Failed to fetch telemetry for $assetId', cause: error);
    }
  }

  Future<AssetTelemetryResponse> fetchAssetOperatorTelemetry(String assetId) {
    return fetchAssetTelemetry(assetId, operatorView: true);
  }
}
