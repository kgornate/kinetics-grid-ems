import '../config/app_config.dart';
import '../core/api/api_client.dart';
import '../core/api/api_exception.dart';
import '../core/api/endpoint_paths.dart';
import '../core/api/query_utils.dart';
import '../models/log_models.dart';
import '../models/log_filter_model.dart';

class LogApiService {
  final String gatewayIp;
  final int port;
  final Duration timeout;
  late final ApiClient _client = ApiClient(
    host: gatewayIp,
    port: port,
    timeout: timeout,
  );

  LogApiService({
    required this.gatewayIp,
    this.port = AppConfig.logHttpPort,
    this.timeout = AppConfig.httpTimeout,
  });

  Uri _uri(
    String path, {
    Map<String, String>? queryParameters,
  }) {
    return _client.uri(path, queryParameters: queryParameters);
  }

  Map<String, String> _cleanQuery(Map<String, String?> query) {
    return QueryUtils.clean(query);
  }

  Future<Map<String, dynamic>> _getJson(
    String path, {
    Map<String, String>? queryParameters,
  }) async {
    try {
      return await _client.getJson(path, queryParameters: queryParameters);
    } on ApiException catch (error) {
      throw LogApiException(error.message);
    }
  }

  Future<Map<String, dynamic>> fetchHealth() async {
    return _getJson(EndpointPaths.logHealth);
  }

  Future<LogAssetsResponse> fetchAssets() async {
    final json = await _getJson(EndpointPaths.logAssets);
    return LogAssetsResponse.fromJson(json);
  }

  Future<StorageStatus> fetchStorageStatus({
    String assetId = AppConfig.chillerAssetId,
  }) async {
    final json = await _getJson(
      EndpointPaths.storageStatus,
      queryParameters: _cleanQuery({
        'asset_id': assetId,
      }),
    );
    return StorageStatus.fromJson(json);
  }

  Future<Map<String, dynamic>> fetchStorageHealth({
    String assetId = AppConfig.chillerAssetId,
  }) async {
    return _getJson(
      EndpointPaths.storageHealth,
      queryParameters: _cleanQuery({
        'asset_id': assetId,
      }),
    );
  }

  Future<LogFilesResponse> fetchLogFiles({
    String assetId = AppConfig.chillerAssetId,
  }) async {
    final json = await _getJson(
      EndpointPaths.logFiles,
      queryParameters: _cleanQuery({
        'asset_id': assetId,
      }),
    );
    return LogFilesResponse.fromJson(json);
  }

  Future<LogApiResponse> fetchTelemetryLogs({
    required String date,
    String assetId = AppConfig.chillerAssetId,
    int limit = 100,
    String? startTime,
    String? endTime,
    String? fields,
    String? modbusStatus,
    String? loggerStatus,
    String? vendor,
    String? commStatus,
    String? operatingStatus,
    String? faultStatus,
    String? search,
    int? offset,
    String? order,
  }) async {
    final json = await _getJson(
      EndpointPaths.logTelemetry,
      queryParameters: _cleanQuery({
        'asset_id': assetId,
        'date': date,
        'limit': limit.toString(),
        'start_time': startTime,
        'end_time': endTime,
        'fields': fields,
        'modbus_status': modbusStatus,
        'logger_status': loggerStatus,
        'vendor': vendor,
        'comm_status': commStatus,
        'operating_status': operatingStatus,
        'fault_status': faultStatus,
        'search': search,
        'offset': offset?.toString(),
        'order': order,
      }),
    );

    return LogApiResponse.fromJson(json);
  }

  Future<LogApiResponse> fetchEventLogs({
    String assetId = AppConfig.chillerAssetId,
    int limit = 100,
    String? date,
    String? startTime,
    String? endTime,
    String? eventType,
    String? status,
    String? source,
    String? command,
    String? vendor,
    String? search,
    String? fields,
    int? offset,
    String? order,
  }) async {
    final json = await _getJson(
      EndpointPaths.logEvents,
      queryParameters: _cleanQuery({
        'asset_id': assetId,
        'limit': limit.toString(),
        'date': date,
        'start_time': startTime,
        'end_time': endTime,
        'event_type': eventType,
        'status': status,
        'source': source,
        'command': command,
        'vendor': vendor,
        'search': search,
        'fields': fields,
        'offset': offset?.toString(),
        'order': order,
      }),
    );

    return LogApiResponse.fromJson(json);
  }

  Future<LogApiResponse> fetchErrorLogs({
    String assetId = AppConfig.chillerAssetId,
    int limit = 100,
    String? date,
    String? startTime,
    String? endTime,
    String? errorType,
    String? errorSource,
    String? search,
    String? fields,
    int? offset,
    String? order,
  }) async {
    final json = await _getJson(
      EndpointPaths.logErrors,
      queryParameters: _cleanQuery({
        'asset_id': assetId,
        'limit': limit.toString(),
        'date': date,
        'start_time': startTime,
        'end_time': endTime,
        'error_type': errorType,
        'error_source': errorSource,
        'search': search,
        'fields': fields,
        'offset': offset?.toString(),
        'order': order,
      }),
    );

    return LogApiResponse.fromJson(json);
  }


  Future<LogApiResponse> fetchTelemetryLogsWithFilter(
    LogFilterModel filter,
  ) async {
    if (filter.date == null || filter.date!.isEmpty) {
      throw LogApiException('date is required for telemetry log queries');
    }
    final json = await _getJson(
      EndpointPaths.logTelemetry,
      queryParameters: _cleanQuery(filter.toQueryParameters()),
    );
    return LogApiResponse.fromJson(json);
  }

  Future<LogApiResponse> fetchEventLogsWithFilter(
    LogFilterModel filter,
  ) async {
    final json = await _getJson(
      EndpointPaths.logEvents,
      queryParameters: _cleanQuery(filter.toQueryParameters()),
    );
    return LogApiResponse.fromJson(json);
  }

  Future<LogApiResponse> fetchErrorLogsWithFilter(
    LogFilterModel filter,
  ) async {
    final json = await _getJson(
      EndpointPaths.logErrors,
      queryParameters: _cleanQuery(filter.toQueryParameters()),
    );
    return LogApiResponse.fromJson(json);
  }

  Future<MetadataResponse> fetchMetadata({
    String assetId = AppConfig.chillerAssetId,
  }) async {
    final json = await _getJson(
      EndpointPaths.logMetadata,
      queryParameters: _cleanQuery({
        'asset_id': assetId,
      }),
    );
    return MetadataResponse.fromJson(json);
  }

  String telemetryCsvDownloadUrl({
    required String date,
    String assetId = AppConfig.chillerAssetId,
  }) {
    return _uri(
      EndpointPaths.telemetryCsvDownload,
      queryParameters: _cleanQuery({
        'asset_id': assetId,
        'date': date,
      }),
    ).toString();
  }
}

class LogApiException implements Exception {
  final String message;

  LogApiException(this.message);

  @override
  String toString() => message;
}
