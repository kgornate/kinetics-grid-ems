import 'dart:async';
import 'dart:convert';
import 'dart:io';

import '../config/app_config.dart';
import '../models/log_models.dart';

class LogApiService {
  final String gatewayIp;
  final int port;
  final Duration timeout;

  LogApiService({
    required this.gatewayIp,
    this.port = AppConfig.logHttpPort,
    this.timeout = AppConfig.httpTimeout,
  });

  Uri _uri(
    String path, {
    Map<String, String>? queryParameters,
  }) {
    return Uri(
      scheme: 'http',
      host: gatewayIp,
      port: port,
      path: path,
      queryParameters: queryParameters,
    );
  }

  Map<String, String> _cleanQuery(Map<String, String?> query) {
    final cleaned = <String, String>{};

    query.forEach((key, value) {
      if (value == null) return;

      final trimmed = value.trim();

      if (trimmed.isEmpty) return;
      if (trimmed.toLowerCase() == 'all') return;

      cleaned[key] = trimmed;
    });

    return cleaned;
  }

  Future<Map<String, dynamic>> _getJson(
    String path, {
    Map<String, String>? queryParameters,
  }) async {
    final uri = _uri(path, queryParameters: queryParameters);

    final client = HttpClient();
    client.connectionTimeout = timeout;

    try {
      final request = await client.getUrl(uri).timeout(timeout);
      final response = await request.close().timeout(timeout);

      final body = await response.transform(utf8.decoder).join().timeout(timeout);

      final decoded = jsonDecode(body);

      if (decoded is! Map) {
        throw const FormatException('HTTP response is not a JSON object');
      }

      final json = Map<String, dynamic>.from(decoded);

      if (response.statusCode < 200 || response.statusCode >= 300) {
        final message =
            json['message']?.toString() ?? 'HTTP ${response.statusCode} from log API';
        throw LogApiException(message);
      }

      return json;
    } on TimeoutException {
      throw LogApiException(
        'HTTP timeout while connecting to $gatewayIp:$port',
      );
    } on SocketException catch (e) {
      throw LogApiException(
        'Socket error while connecting to $gatewayIp:$port: ${e.message}',
      );
    } on FormatException catch (e) {
      throw LogApiException('Invalid JSON from log API: ${e.message}');
    } finally {
      client.close(force: true);
    }
  }

  Future<Map<String, dynamic>> fetchHealth() async {
    return _getJson('/api/health');
  }

  Future<StorageStatus> fetchStorageStatus() async {
    final json = await _getJson('/api/storage/status');
    return StorageStatus.fromJson(json);
  }

  Future<LogFilesResponse> fetchLogFiles() async {
    final json = await _getJson('/api/logs/files');
    return LogFilesResponse.fromJson(json);
  }

  Future<LogApiResponse> fetchTelemetryLogs({
    required String date,
    int limit = 100,
    String? startTime,
    String? endTime,
    String? fields,
    String? modbusStatus,
    String? loggerStatus,
    String? search,
  }) async {
    final json = await _getJson(
      '/api/logs/telemetry',
      queryParameters: _cleanQuery({
        'date': date,
        'limit': limit.toString(),
        'start_time': startTime,
        'end_time': endTime,
        'fields': fields,
        'modbus_status': modbusStatus,
        'logger_status': loggerStatus,
        'search': search,
      }),
    );

    return LogApiResponse.fromJson(json);
  }

  Future<LogApiResponse> fetchEventLogs({
    int limit = 100,
    String? date,
    String? startTime,
    String? endTime,
    String? eventType,
    String? status,
    String? source,
    String? search,
    String? fields,
  }) async {
    final json = await _getJson(
      '/api/logs/events',
      queryParameters: _cleanQuery({
        'limit': limit.toString(),
        'date': date,
        'start_time': startTime,
        'end_time': endTime,
        'event_type': eventType,
        'status': status,
        'source': source,
        'search': search,
        'fields': fields,
      }),
    );

    return LogApiResponse.fromJson(json);
  }

  Future<LogApiResponse> fetchErrorLogs({
    int limit = 100,
    String? date,
    String? startTime,
    String? endTime,
    String? errorType,
    String? errorSource,
    String? search,
    String? fields,
  }) async {
    final json = await _getJson(
      '/api/logs/errors',
      queryParameters: _cleanQuery({
        'limit': limit.toString(),
        'date': date,
        'start_time': startTime,
        'end_time': endTime,
        'error_type': errorType,
        'error_source': errorSource,
        'search': search,
        'fields': fields,
      }),
    );

    return LogApiResponse.fromJson(json);
  }

  Future<MetadataResponse> fetchMetadata() async {
    final json = await _getJson('/api/logs/metadata');
    return MetadataResponse.fromJson(json);
  }

  String telemetryCsvDownloadUrl({
    required String date,
  }) {
    return _uri(
      '/api/logs/download/telemetry',
      queryParameters: {
        'date': date,
      },
    ).toString();
  }
}

class LogApiException implements Exception {
  final String message;

  LogApiException(this.message);

  @override
  String toString() => message;
}