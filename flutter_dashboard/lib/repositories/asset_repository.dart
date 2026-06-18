import '../models/models.dart';
import '../services/gateway_api_service.dart';
import 'repository_exception.dart';

/// Repository for runtime asset discovery.
class AssetRepository {
  final GatewayApiService api;

  const AssetRepository({required this.api});

  factory AssetRepository.forGateway(String gatewayIp) {
    return AssetRepository(api: GatewayApiService(gatewayIp: gatewayIp));
  }

  Future<AssetListResponse> fetchAssets() async {
    try {
      return await api.fetchAssetsTyped();
    } catch (error) {
      throw RepositoryException('Failed to fetch assets', cause: error);
    }
  }

  Future<List<AssetModel>> fetchAssetList() async {
    final response = await fetchAssets();
    return response.assets;
  }

  Future<AssetResponse> fetchAsset(String assetId) async {
    try {
      return await api.fetchAssetTyped(assetId);
    } catch (error) {
      throw RepositoryException('Failed to fetch asset $assetId', cause: error);
    }
  }

  Future<AssetModel?> findAsset(String assetId) async {
    final response = await fetchAssets();
    return response.findById(assetId);
  }

  Future<List<AssetModel>> fetchActiveAssets() async {
    final assets = await fetchAssetList();
    return assets.where((asset) => asset.running || asset.online).toList(growable: false);
  }
}
