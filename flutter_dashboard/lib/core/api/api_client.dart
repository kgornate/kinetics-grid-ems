import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'api_exception.dart';

/// Small dependency-free HTTP client for gateway REST APIs.
///
/// It centralizes JSON parsing, timeouts, HTTP errors, and socket errors. This
/// keeps feature services focused on endpoint-specific request/response logic.
class ApiClient {
  final String host;
  final int port;
  final Duration timeout;
  final String scheme;

  const ApiClient({
    required this.host,
    required this.port,
    this.timeout = const Duration(seconds: 8),
    this.scheme = 'http',
  });

  Uri uri(
    String path, {
    Map<String, String>? queryParameters,
  }) {
    return Uri(
      scheme: scheme,
      host: host,
      port: port,
      path: path,
      queryParameters: queryParameters,
    );
  }

  Future<Map<String, dynamic>> getJson(
    String path, {
    Map<String, String>? queryParameters,
  }) async {
    final target = uri(path, queryParameters: queryParameters);
    final client = HttpClient()..connectionTimeout = timeout;

    try {
      final request = await client.getUrl(target).timeout(timeout);
      final response = await request.close().timeout(timeout);
      final body = await response.transform(utf8.decoder).join().timeout(timeout);
      final decoded = jsonDecode(body);

      if (decoded is! Map) {
        throw const FormatException('HTTP response is not a JSON object');
      }

      final json = Map<String, dynamic>.from(decoded);
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final message = json['message']?.toString() ??
            'HTTP ${response.statusCode} from $host:$port';
        throw ApiException(message, statusCode: response.statusCode);
      }
      return json;
    } on TimeoutException catch (error) {
      throw ApiException(
        'HTTP timeout while connecting to $host:$port',
        cause: error,
      );
    } on SocketException catch (error) {
      throw ApiException(
        'Socket error while connecting to $host:$port: ${error.message}',
        cause: error,
      );
    } on FormatException catch (error) {
      throw ApiException('Invalid JSON from API: ${error.message}', cause: error);
    } finally {
      client.close(force: true);
    }
  }
}
