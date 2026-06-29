class AssetSummary {
  AssetSummary({
    required this.assetId,
    required this.displayName,
    required this.online,
    required this.signalCount,
    required this.badSignalCount,
    this.lastUpdateUtc,
    this.keySignals = const {},
    this.assetType,
    this.description,
  });

  final String assetId;
  final String displayName;
  final bool online;
  final int signalCount;
  final int badSignalCount;
  final String? lastUpdateUtc;
  final Map<String, dynamic> keySignals;
  final String? assetType;
  final String? description;

  factory AssetSummary.fromJson(Map<String, dynamic> json) {
    return AssetSummary(
      assetId: json['asset_id']?.toString() ?? json['id']?.toString() ?? 'unknown',
      displayName: json['display_name']?.toString() ??
          json['name']?.toString() ??
          json['asset_id']?.toString() ??
          'Unknown',
      online: json['online'] == true || json['status']?.toString().toLowerCase() == 'online',
      signalCount: _asInt(json['signal_count'] ?? json['signals_count']),
      badSignalCount: _asInt(json['bad_signal_count'] ?? json['bad_signals_count']),
      lastUpdateUtc: json['last_update_utc']?.toString() ?? json['timestamp_utc']?.toString(),
      keySignals: (json['key_signals'] is Map)
          ? Map<String, dynamic>.from(json['key_signals'] as Map)
          : const {},
      assetType: json['asset_type']?.toString() ?? json['type']?.toString(),
      description: json['description']?.toString(),
    );
  }

  AssetSummary copyWith({
    String? assetId,
    String? displayName,
    bool? online,
    int? signalCount,
    int? badSignalCount,
    String? lastUpdateUtc,
    Map<String, dynamic>? keySignals,
    String? assetType,
    String? description,
  }) {
    return AssetSummary(
      assetId: assetId ?? this.assetId,
      displayName: displayName ?? this.displayName,
      online: online ?? this.online,
      signalCount: signalCount ?? this.signalCount,
      badSignalCount: badSignalCount ?? this.badSignalCount,
      lastUpdateUtc: lastUpdateUtc ?? this.lastUpdateUtc,
      keySignals: keySignals ?? this.keySignals,
      assetType: assetType ?? this.assetType,
      description: description ?? this.description,
    );
  }

  static int _asInt(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '') ?? 0;
  }
}
