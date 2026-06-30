class StorageStatus {
  const StorageStatus({
    required this.enabled,
    required this.canWrite,
    required this.mountOk,
    required this.path,
    this.storeMode,
    this.dbSizeMb,
    this.freeSpaceMb,
    this.usedPercent,
    this.snapshotIntervalSec,
    this.retentionDays,
    this.skippedWriteCount,
    this.lastSkipReason,
    this.tables = const {},
    this.reasons = const [],
    this.raw = const {},
  });

  final bool enabled;
  final bool canWrite;
  final bool mountOk;
  final String path;
  final String? storeMode;
  final int? dbSizeMb;
  final int? freeSpaceMb;
  final num? usedPercent;
  final num? snapshotIntervalSec;
  final int? retentionDays;
  final int? skippedWriteCount;
  final String? lastSkipReason;
  final Map<String, dynamic> tables;
  final List<String> reasons;
  final Map<String, dynamic> raw;

  factory StorageStatus.fromJson(Map<String, dynamic> json) {
    return StorageStatus(
      enabled: json['enabled'] == true,
      canWrite: json['can_write'] == true,
      mountOk: json['mount_ok'] != false,
      path: json['path']?.toString() ?? '',
      storeMode: json['store_mode']?.toString(),
      dbSizeMb: _asIntOrNull(json['db_size_mb']),
      freeSpaceMb: _asIntOrNull(json['free_space_mb']),
      usedPercent: json['used_percent'] is num ? json['used_percent'] as num : num.tryParse(json['used_percent']?.toString() ?? ''),
      snapshotIntervalSec: json['snapshot_interval_sec'] is num ? json['snapshot_interval_sec'] as num : num.tryParse(json['snapshot_interval_sec']?.toString() ?? ''),
      retentionDays: _asIntOrNull(json['retention_days']),
      skippedWriteCount: _asIntOrNull(json['skipped_write_count']),
      lastSkipReason: json['last_skip_reason']?.toString(),
      tables: json['tables'] is Map ? Map<String, dynamic>.from(json['tables'] as Map) : const {},
      reasons: json['reasons'] is List ? (json['reasons'] as List).map((e) => e.toString()).toList() : const [],
      raw: json,
    );
  }

  static int? _asIntOrNull(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '');
  }
}
