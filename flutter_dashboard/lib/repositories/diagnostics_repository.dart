import '../models/models.dart';
import '../services/gateway_api_service.dart';
import 'repository_exception.dart';

/// Repository for diagnostics APIs.
class DiagnosticsRepository {
  final GatewayApiService api;

  const DiagnosticsRepository({required this.api});

  factory DiagnosticsRepository.forGateway(String gatewayIp) {
    return DiagnosticsRepository(api: GatewayApiService(gatewayIp: gatewayIp));
  }

  Future<DiagnosticsResponse> fetchDiagnostics() async {
    try {
      return await api.fetchDiagnosticsTyped();
    } catch (error) {
      throw RepositoryException('Failed to fetch diagnostics', cause: error);
    }
  }

  Future<AssetDiagnosticsResponse> fetchAssetDiagnostics(String assetId) async {
    try {
      return await api.fetchAssetDiagnosticsTyped(assetId);
    } catch (error) {
      throw RepositoryException('Failed to fetch diagnostics for $assetId', cause: error);
    }
  }
}
