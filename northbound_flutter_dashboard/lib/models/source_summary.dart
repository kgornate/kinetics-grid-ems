class SourceSummary {
  const SourceSummary({
    required this.sourceId,
    required this.displayName,
    required this.host,
    required this.port,
    this.unitId,
    this.interfaceName,
    required this.online,
    required this.assetCount,
    required this.onlineAssetCount,
    required this.signalCount,
    required this.badSignalCount,
    this.lastUpdateUtc,
  });

  final String sourceId;
  final String displayName;
  final String host;
  final int port;
  final int? unitId;
  final String? interfaceName;
  final bool online;
  final int assetCount;
  final int onlineAssetCount;
  final int signalCount;
  final int badSignalCount;
  final String? lastUpdateUtc;

  factory SourceSummary.fromJson(Map<String, dynamic> json) {
    return SourceSummary(
      sourceId: json['source_id']?.toString() ?? json['id']?.toString() ?? 'unknown',
      displayName: json['display_name']?.toString() ?? json['name']?.toString() ?? json['source_id']?.toString() ?? 'Unknown source',
      host: json['host']?.toString() ?? json['source_host']?.toString() ?? '',
      port: _asInt(json['port'] ?? json['source_port']),
      unitId: json.containsKey('unit_id') ? _asInt(json['unit_id']) : null,
      interfaceName: json['interface']?.toString() ?? json['interface_name']?.toString(),
      online: json['online'] == true || json['status']?.toString().toLowerCase() == 'online',
      assetCount: _asInt(json['asset_count']),
      onlineAssetCount: _asInt(json['online_asset_count']),
      signalCount: _asInt(json['signal_count']),
      badSignalCount: _asInt(json['bad_signal_count']),
      lastUpdateUtc: json['last_update_utc']?.toString(),
    );
  }

  static int _asInt(dynamic value) {
    if (value == null) return 0;
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value.toString()) ?? 0;
  }
}
