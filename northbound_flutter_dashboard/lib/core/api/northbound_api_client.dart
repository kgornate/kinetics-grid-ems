
import 'dart:convert';

import 'package:http/http.dart' as http;


class _NorthboundCacheEntry {
  _NorthboundCacheEntry(this.createdAt, this.payload);

  final DateTime createdAt;
  final Map<String, dynamic> payload;

  bool isFresh(Duration ttl) => DateTime.now().difference(createdAt) < ttl;
}

class NorthboundApiClient {
  static const Duration sourcesSummaryCacheTtl = Duration(seconds: 8);
  static const Duration assetsCacheTtl = Duration(seconds: 60);

  static final Map<String, _NorthboundCacheEntry> _sourcesSummaryCache = {};
  static final Map<String, _NorthboundCacheEntry> _assetsCache = {};

  NorthboundApiClient({
    required this.baseUrl,
    this.token,
    http.Client? client,
  }) : _client = client ?? http.Client();

  final String baseUrl;
  final String? token;
  final http.Client _client;

  String _cacheScope() => '$baseUrl|${token ?? ''}';

  static Map<String, dynamic> _clone(Map<String, dynamic> payload) {
    return jsonDecode(jsonEncode(payload)) as Map<String, dynamic>;
  }

  static void clearCaches() {
    _sourcesSummaryCache.clear();
    _assetsCache.clear();
  }

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

  Future<Map<String, dynamic>> getSourcesSummary({bool forceRefresh = false}) async {
    final key = '${_cacheScope()}|sources-summary';
    final cached = _sourcesSummaryCache[key];
    if (!forceRefresh && cached != null && cached.isFresh(sourcesSummaryCacheTtl)) {
      return _clone(cached.payload);
    }

    final response = await _client.get(
      _uri('/api/sources/summary'),
      headers: _headers(),
    );
    _throwIfNeeded(response);
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    _sourcesSummaryCache[key] = _NorthboundCacheEntry(DateTime.now(), decoded);
    return _clone(decoded);
  }

  Future<Map<String, dynamic>> getAssets({String? sourceId, bool forceRefresh = false}) async {
    final key = '${_cacheScope()}|assets|${sourceId ?? 'all'}';
    final cached = _assetsCache[key];
    if (!forceRefresh && cached != null && cached.isFresh(assetsCacheTtl)) {
      return _clone(cached.payload);
    }

    final response = await _client.get(
      _uri('/api/assets', sourceId == null ? null : {'source_id': sourceId}),
      headers: _headers(),
    );
    _throwIfNeeded(response);
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    _assetsCache[key] = _NorthboundCacheEntry(DateTime.now(), decoded);
    return _clone(decoded);
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


  Future<Map<String, dynamic>> getFastBessStatus() async {
    final response = await _client.get(
      _uri('/api/fast-bess/status'),
      headers: _headers(),
    );
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getFastBessProfile() async {
    final response = await _client.get(
      _uri('/api/fast-bess/profile'),
      headers: _headers(),
    );
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getFastBessLatest({String format = 'compact'}) async {
    final response = await _client.get(
      _uri('/api/fast-bess/latest', {'format': format}),
      headers: _headers(),
    );
    _throwIfNeeded(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getFastBessHistory({
    String? sourceId,
    int? fromEpochMs,
    int? toEpochMs,
    int limit = 1000,
    String order = 'desc',
    String format = 'compact',
  }) async {
    final query = <String, dynamic>{
      'limit': limit,
      'order': order,
      'format': format,
    };
    if (sourceId != null && sourceId.isNotEmpty) query['source_id'] = sourceId;
    if (fromEpochMs != null) query['from_epoch_ms'] = fromEpochMs;
    if (toEpochMs != null) query['to_epoch_ms'] = toEpochMs;

    final response = await _client.get(
      _uri('/api/fast-bess/history', query),
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
