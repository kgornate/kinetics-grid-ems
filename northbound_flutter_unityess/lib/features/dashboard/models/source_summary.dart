class SourceSummary {
  const SourceSummary({
    required this.sourceId,
    required this.displayName,
    required this.host,
    required this.port,
    required this.assetCount,
    required this.online,
    required this.onlineAssetCount,
    required this.signalCount,
    required this.badSignalCount,
    this.lastUpdateUtc,
  });

  final String sourceId;
  final String displayName;
  final String host;
  final int port;
  final int assetCount;
  final bool online;
  final int onlineAssetCount;
  final int signalCount;
  final int badSignalCount;
  final String? lastUpdateUtc;

  String get shortTitle => displayName.isNotEmpty ? displayName : sourceId;

  bool get isHealthy => online && badSignalCount == 0;

  int? get sourceIndex {
    final match = RegExp(r'external_ems_(\d+)', caseSensitive: false).firstMatch(sourceId);
    return match == null ? null : int.tryParse(match.group(1)!);
  }

  static String _normalizeDisplayName(String raw, String sourceId) {
    final idxMatch = RegExp(r'external_ems_(\d+)', caseSensitive: false).firstMatch(sourceId);
    final idx = idxMatch?.group(1);

    if (idx != null) {
      return 'BESS EMS $idx';
    }

    final lower = raw.toLowerCase().trim();
    if (lower == 'chinese ems 1') return 'BESS EMS 1';
    if (lower == 'chinese ems 2') return 'BESS EMS 2';
    return raw;
  }

  factory SourceSummary.fromJson(Map<String, dynamic> json) {
    final sourceId = json['source_id']?.toString() ?? '';
    final rawDisplayName = json['display_name']?.toString() ?? '';
    return SourceSummary(
      sourceId: sourceId,
      displayName: _normalizeDisplayName(rawDisplayName, sourceId),
      host: json['host']?.toString() ?? '',
      port: (json['port'] as num?)?.toInt() ?? 0,
      assetCount: (json['asset_count'] as num?)?.toInt() ?? 0,
      online: json['online'] == true,
      onlineAssetCount: (json['online_asset_count'] as num?)?.toInt() ?? 0,
      signalCount: (json['signal_count'] as num?)?.toInt() ?? 0,
      badSignalCount: (json['bad_signal_count'] as num?)?.toInt() ?? 0,
      lastUpdateUtc: json['last_update_utc']?.toString(),
    );
  }
}
