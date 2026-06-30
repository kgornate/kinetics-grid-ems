class ApiProfile {
  const ApiProfile({
    required this.name,
    required this.restBaseUrl,
    required this.wsUrl,
    required this.logsBaseUrl,
    required this.httpTimeout,
  });

  final String name;
  final String restBaseUrl;
  final String wsUrl;
  final String logsBaseUrl;
  final Duration httpTimeout;

  static const localEth0 = ApiProfile(
    name: 'Local eth0',
    restBaseUrl: 'http://192.168.10.2:8000',
    wsUrl: 'ws://192.168.10.2:8000/ws/telemetry',
    // NorthBound v0.5 exposes logs/storage on the main FastAPI port.
    // If a separate log server is enabled later, change only this field.
    logsBaseUrl: 'http://192.168.10.2:8000',
    httpTimeout: Duration(seconds: 5),
  );

  static const cloudflare = ApiProfile(
    name: 'Cloudflare',
    restBaseUrl: 'https://ems-api.unityess.cloud',
    wsUrl: 'wss://ems-api.unityess.cloud/ws/telemetry',
    // Current NorthBound v0.5 logs APIs are available on ems-api as /api/logs.
    // Use https://ems-logs.unityess.cloud here only if that tunnel/domain is
    // wired to the same NorthBound v0.5 log routes.
    logsBaseUrl: 'https://ems-api.unityess.cloud',
    httpTimeout: Duration(seconds: 30),
  );

  ApiProfile copyWith({
    String? name,
    String? restBaseUrl,
    String? wsUrl,
    String? logsBaseUrl,
    Duration? httpTimeout,
  }) {
    return ApiProfile(
      name: name ?? this.name,
      restBaseUrl: restBaseUrl ?? this.restBaseUrl,
      wsUrl: wsUrl ?? this.wsUrl,
      logsBaseUrl: logsBaseUrl ?? this.logsBaseUrl,
      httpTimeout: httpTimeout ?? this.httpTimeout,
    );
  }

  static Duration recommendedTimeoutFor(String restBaseUrl) {
    final lower = restBaseUrl.toLowerCase();
    if (lower.contains('ems-api.unityess.cloud') || lower.startsWith('https://')) {
      return const Duration(seconds: 30);
    }
    return const Duration(seconds: 5);
  }
}

// Backward-compatible alias for older imports in this codebase.
typedef AppConfig = ApiProfile;
