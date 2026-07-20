
import 'dart:convert';

import 'package:http/http.dart' as http;

class NorthboundApiClient {
  NorthboundApiClient({
    required this.baseUrl,
    this.token,
    http.Client? client,
  }) : _client = client ?? http.Client();

  final String baseUrl;
  final String? token;
  final http.Client _client;

  Map<String, String> _headers({bool json = false}) {
    final headers = <String, String>{};
    if (json) headers['Content-Type'] = 'application/json';
    if (token != null && token!.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
    }
    return headers;
  }

  Uri _uri(String path, [Map<String, dynamic>? query]) {
    final root = Uri.parse(baseUrl);
    return root.replace(
      path: path.startsWith('/') ? path : '/$path',
      queryParameters: query == null
          ? null
          : query.map((key, value) => MapEntry(key, '$value')),
    );
  }

  Future<Map<String, dynamic>> login({
    required String username,
    required String password,
  }) async {
    final response = await _client.post(
      _uri('/api/auth/login'),
      headers: _headers(json: true),
      body: jsonEncode({
        'username': username,
        'password': password,
      }),
    );
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getHealth() async {
    final response = await _client.get(_uri('/api/health'), headers: _headers());
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getSourcesSummary() async {
    final response = await _client.get(
      _uri('/api/sources/summary'),
      headers: _headers(),
    );
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getAssets({String? sourceId}) async {
    final response = await _client.get(
      _uri('/api/assets', sourceId == null ? null : {'source_id': sourceId}),
      headers: _headers(),
    );
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getAssetTelemetry(
    String assetId, {
    bool compact = true,
    bool keyOnly = false,
    String? category,
    int? page,
    int? pageSize,
  }) async {
    final query = <String, dynamic>{
      'compact': compact,
      'key_only': keyOnly,
    };
    if (category != null && category.isNotEmpty) query['category'] = category;
    if (page != null) query['page'] = page;
    if (pageSize != null) query['page_size'] = pageSize;

    final response = await _client.get(
      _uri('/api/assets/$assetId/telemetry', query),
      headers: _headers(),
    );
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getKeySignals() async {
    final response = await _client.get(
      _uri('/api/telemetry/key-signals'),
      headers: _headers(),
    );
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getAlarms() async {
    final response = await _client.get(_uri('/api/alarms'), headers: _headers());
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  void _throwIfNeeded(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) return;
    throw Exception('HTTP ${response.statusCode}: ${response.body}');
  }

  void dispose() => _client.close();
}
