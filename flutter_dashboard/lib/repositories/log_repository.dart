import '../config/app_config.dart';
import '../models/models.dart';
import '../services/log_api_service.dart';
import 'repository_exception.dart';

/// Repository for log, storage status, and filtered log-query APIs.
class LogRepository {
  final LogApiService api;

  const LogRepository({required this.api});

  factory LogRepository.forGateway(String gatewayIp) {
    return LogRepository(api: LogApiService(gatewayIp: gatewayIp));
  }

  Future<Map<String, dynamic>> fetchLogServerHealth() async {
    try {
      return await api.fetchHealth();
    } catch (error) {
      throw RepositoryException('Failed to fetch log server health', cause: error);
    }
  }


  Future<Map<String, dynamic>> fetchHealth() => fetchLogServerHealth();

  Future<LogAssetsResponse> fetchAssets() => fetchLogAssets();

  Future<LogAssetsResponse> fetchLogAssets() async {
    try {
      return await api.fetchAssets();
    } catch (error) {
      throw RepositoryException('Failed to fetch log assets', cause: error);
    }
  }

  Future<StorageStatus> fetchStorageStatus({
    String assetId = AppConfig.chillerAssetId,
  }) async {
    try {
      return await api.fetchStorageStatus(assetId: assetId);
    } catch (error) {
      throw RepositoryException('Failed to fetch storage status for $assetId', cause: error);
    }
  }

  Future<Map<String, dynamic>> fetchStorageHealth({
    String assetId = AppConfig.chillerAssetId,
  }) async {
    try {
      return await api.fetchStorageHealth(assetId: assetId);
    } catch (error) {
      throw RepositoryException('Failed to fetch storage health for $assetId', cause: error);
    }
  }

  Future<LogFilesResponse> fetchLogFiles({
    String assetId = AppConfig.chillerAssetId,
  }) async {
    try {
      return await api.fetchLogFiles(assetId: assetId);
    } catch (error) {
      throw RepositoryException('Failed to fetch log files for $assetId', cause: error);
    }
  }

  Future<LogApiResponse> fetchTelemetryLogs(LogFilterModel filter) async {
    try {
      return await api.fetchTelemetryLogsWithFilter(filter);
    } catch (error) {
      throw RepositoryException('Failed to fetch telemetry logs', cause: error);
    }
  }

  Future<LogApiResponse> fetchEventLogs(LogFilterModel filter) async {
    try {
      return await api.fetchEventLogsWithFilter(filter);
    } catch (error) {
      throw RepositoryException('Failed to fetch event logs', cause: error);
    }
  }

  Future<LogApiResponse> fetchErrorLogs(LogFilterModel filter) async {
    try {
      return await api.fetchErrorLogsWithFilter(filter);
    } catch (error) {
      throw RepositoryException('Failed to fetch error logs', cause: error);
    }
  }

  Future<MetadataResponse> fetchMetadata({
    String assetId = AppConfig.chillerAssetId,
  }) async {
    try {
      return await api.fetchMetadata(assetId: assetId);
    } catch (error) {
      throw RepositoryException('Failed to fetch metadata for $assetId', cause: error);
    }
  }

  String telemetryCsvDownloadUrl({
    required String date,
    String assetId = AppConfig.chillerAssetId,
  }) {
    return api.telemetryCsvDownloadUrl(date: date, assetId: assetId);
  }
}
