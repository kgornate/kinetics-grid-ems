import '../models/models.dart';
import '../services/gateway_api_service.dart';
import 'repository_exception.dart';

/// Repository for health monitoring APIs.
class HealthRepository {
  final GatewayApiService api;

  const HealthRepository({required this.api});

  factory HealthRepository.forGateway(String gatewayIp) {
    return HealthRepository(api: GatewayApiService(gatewayIp: gatewayIp));
  }

  Future<GatewayHealthModel> fetchOverallHealth() async {
    try {
      return await api.fetchHealthTyped();
    } catch (error) {
      throw RepositoryException('Failed to fetch overall health', cause: error);
    }
  }

  Future<GatewayHealthModel> fetchGatewayHealth() async {
    try {
      return await api.fetchGatewayHealthDetailsTyped();
    } catch (error) {
      throw RepositoryException('Failed to fetch gateway health', cause: error);
    }
  }

  Future<AssetsHealthResponse> fetchAssetsHealth() async {
    try {
      return await api.fetchAssetsHealthTyped();
    } catch (error) {
      throw RepositoryException('Failed to fetch assets health', cause: error);
    }
  }

  Future<AssetHealthModel> fetchAssetHealth(String assetId) async {
    try {
      return await api.fetchAssetHealthTyped(assetId);
    } catch (error) {
      throw RepositoryException('Failed to fetch health for $assetId', cause: error);
    }
  }
}
