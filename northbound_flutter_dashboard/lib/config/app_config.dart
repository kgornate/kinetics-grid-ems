class AppConfig {
  const AppConfig({
    required this.apiBaseUrl,
    required this.wsUrl,
  });

  final String apiBaseUrl;
  final String wsUrl;

  static const localEth0 = AppConfig(
    apiBaseUrl: 'http://192.168.10.2:8000',
    wsUrl: 'ws://192.168.10.2:8000/ws/telemetry',
  );

  static const cloudflare = AppConfig(
    apiBaseUrl: 'https://ems-api.unityess.cloud',
    wsUrl: 'wss://ems-api.unityess.cloud/ws/telemetry',
  );

  AppConfig copyWith({String? apiBaseUrl, String? wsUrl}) {
    return AppConfig(
      apiBaseUrl: apiBaseUrl ?? this.apiBaseUrl,
      wsUrl: wsUrl ?? this.wsUrl,
    );
  }
}
