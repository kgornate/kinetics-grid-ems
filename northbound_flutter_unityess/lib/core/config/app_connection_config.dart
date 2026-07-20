import 'package:flutter/foundation.dart';

enum ConnectionMode {
  cloudflare,
  localEth0,
  custom,
}

@immutable
class AppConnectionConfig {
  final ConnectionMode mode;
  final String baseUrl;
  final String label;

  const AppConnectionConfig({
    required this.mode,
    required this.baseUrl,
    required this.label,
  });

  static const cloudflare = AppConnectionConfig(
    mode: ConnectionMode.cloudflare,
    baseUrl: 'https://ems-api.unityess.cloud',
    label: 'Cloudflare',
  );

  static const localEth0 = AppConnectionConfig(
    mode: ConnectionMode.localEth0,
    baseUrl: 'http://192.168.10.2:8000',
    label: 'Local eth0',
  );

  factory AppConnectionConfig.custom(String url) {
    return AppConnectionConfig(
      mode: ConnectionMode.custom,
      baseUrl: url.trim(),
      label: 'Custom',
    );
  }

  String get websocketBaseUrl {
    if (baseUrl.startsWith('https://')) {
      return baseUrl.replaceFirst('https://', 'wss://');
    }
    if (baseUrl.startsWith('http://')) {
      return baseUrl.replaceFirst('http://', 'ws://');
    }
    return baseUrl;
  }

  Map<String, dynamic> toJson() => {
        'mode': mode.name,
        'baseUrl': baseUrl,
        'label': label,
      };

  factory AppConnectionConfig.fromJson(Map<String, dynamic> json) {
    final modeName = (json['mode'] as String?) ?? ConnectionMode.cloudflare.name;
    final mode = ConnectionMode.values.firstWhere(
      (m) => m.name == modeName,
      orElse: () => ConnectionMode.cloudflare,
    );

    return AppConnectionConfig(
      mode: mode,
      baseUrl: (json['baseUrl'] as String?) ?? cloudflare.baseUrl,
      label: (json['label'] as String?) ?? cloudflare.label,
    );
  }
}
