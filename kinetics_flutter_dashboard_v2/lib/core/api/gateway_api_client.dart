import 'dart:async';
import 'dart:convert';
import 'dart:io';

class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => statusCode == null
      ? message
      : 'HTTP $statusCode: $message';
}

class GatewayApiClient {
  GatewayApiClient({String baseUrl = 'http://192.168.10.2:8000'})
      : _baseUrl = _normaliseBaseUrl(baseUrl);

  final HttpClient _http = HttpClient()
    ..connectionTimeout = const Duration(seconds: 300)
    ..idleTimeout = const Duration(seconds: 300);

  String _baseUrl;
  String? token;

  String get baseUrl => _baseUrl;

  void configure({required String baseUrl, String? bearerToken}) {
    _baseUrl = _normaliseBaseUrl(baseUrl);
    token = bearerToken;
  }

  Future<Map<String, dynamic>> login({
    required String username,
    required String password,
  }) async {
    return requestJson(
      'POST',
      '/api/auth/login',
      body: <String, dynamic>{'username': username, 'password': password},
      authenticated: false,
    );
  }

  Future<Map<String, dynamic>> getJson(
    String path, {
    Map<String, String>? query,
    Duration timeout = const Duration(seconds: 300),
  }) {
    return requestJson('GET', path, query: query, timeout: timeout);
  }

  Future<Map<String, dynamic>> postJson(
    String path, {
    Map<String, String>? query,
    Object? body,
    Duration timeout = const Duration(seconds: 300),
  }) {
    return requestJson(
      'POST',
      path,
      query: query,
      body: body,
      timeout: timeout,
    );
  }

  Future<Map<String, dynamic>> requestJson(
    String method,
    String path, {
    Map<String, String>? query,
    Object? body,
    bool authenticated = true,
    Duration timeout = const Duration(seconds: 300),
  }) async {
    final uri = _buildUri(path, query);
    final request = await _http.openUrl(method, uri).timeout(timeout);
    request.headers.set(HttpHeaders.acceptHeader, 'application/json');
    if (authenticated && token != null && token!.isNotEmpty) {
      request.headers.set(HttpHeaders.authorizationHeader, 'Bearer $token');
    }
    if (body != null) {
      request.headers.contentType = ContentType.json;
      request.write(jsonEncode(body));
    }

    final response = await request.close().timeout(timeout);
    final responseText = await response.transform(utf8.decoder).join().timeout(timeout);
    dynamic decoded;
    if (responseText.trim().isNotEmpty) {
      try {
        decoded = jsonDecode(responseText);
      } on FormatException {
        decoded = <String, dynamic>{'message': responseText};
      }
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      final detail = decoded is Map
          ? (decoded['detail'] ?? decoded['message'] ?? responseText)
          : responseText;
      throw ApiException(
        detail?.toString() ?? 'Request failed',
        statusCode: response.statusCode,
      );
    }

    if (decoded is Map<String, dynamic>) return decoded;
    if (decoded is Map) return Map<String, dynamic>.from(decoded);
    return <String, dynamic>{'data': decoded};
  }

  Future<WebSocket> openTelemetrySocket({String mode = 'delta'}) async {
    final bearerToken = token;
    if (bearerToken == null || bearerToken.isEmpty) {
      throw const ApiException('Cannot open WebSocket without a token');
    }
    final base = Uri.parse(_baseUrl);
    final scheme = base.scheme == 'https' ? 'wss' : 'ws';
    final uri = base.replace(
      scheme: scheme,
      path: '${base.path}/ws/telemetry'.replaceAll('//', '/'),
      queryParameters: <String, String>{
        'token': bearerToken,
        'mode': mode,
      },
    );
    return WebSocket.connect(uri.toString()).timeout(const Duration(seconds: 60));
  }

  Uri _buildUri(String path, Map<String, String>? query) {
    final base = Uri.parse(_baseUrl);
    final cleanPath = path.startsWith('/') ? path : '/$path';
    final basePath = base.path == '/' ? '' : base.path;
    return base.replace(
      path: '$basePath$cleanPath'.replaceAll('//', '/'),
      queryParameters: query,
    );
  }

  void close() => _http.close(force: true);

  static String _normaliseBaseUrl(String value) {
    var result = value.trim();
    if (result.isEmpty) result = 'http://192.168.10.2:8000';
    if (!result.contains('://')) result = 'http://$result';
    while (result.endsWith('/')) {
      result = result.substring(0, result.length - 1);
    }
    return result;
  }
}
