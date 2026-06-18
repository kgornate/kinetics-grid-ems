import '../services/gateway_api_service.dart';
import '../models/models.dart';
import 'repository_exception.dart';

/// Gateway-level repository for status and health summary APIs.
class GatewayRepository {
  final GatewayApiService api;

  const GatewayRepository({required this.api});

  factory GatewayRepository.forGateway(String gatewayIp) {
    return GatewayRepository(api: GatewayApiService(gatewayIp: gatewayIp));
  }

  Future<Map<String, dynamic>> fetchGatewayStatus() async {
    try {
      return await api.fetchGatewayStatus();
    } catch (error) {
      throw RepositoryException('Failed to fetch gateway status', cause: error);
    }
  }

  Future<Map<String, dynamic>> fetchSimpleGatewayHealth() async {
    try {
      return await api.fetchGatewayHealth();
    } catch (error) {
      throw RepositoryException('Failed to fetch simple gateway health', cause: error);
    }
  }

  Future<GatewayHealthModel> fetchHealth() async {
    try {
      return await api.fetchHealthTyped();
    } catch (error) {
      throw RepositoryException('Failed to fetch gateway health', cause: error);
    }
  }

  Future<GatewayHealthModel> fetchGatewayHealthDetails() async {
    try {
      return await api.fetchGatewayHealthDetailsTyped();
    } catch (error) {
      throw RepositoryException('Failed to fetch gateway health details', cause: error);
    }
  }
}
