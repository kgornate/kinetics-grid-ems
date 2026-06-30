class PointHistoryRecord {
  const PointHistoryRecord({
    required this.timestampUtc,
    required this.assetId,
    required this.signalName,
    required this.category,
    required this.value,
    required this.unit,
    required this.quality,
    required this.payload,
  });

  final String timestampUtc;
  final String assetId;
  final String signalName;
  final String? category;
  final dynamic value;
  final String? unit;
  final String? quality;
  final Map<String, dynamic> payload;

  factory PointHistoryRecord.fromJson(Map<String, dynamic> json) {
    return PointHistoryRecord(
      timestampUtc: json['timestamp_utc']?.toString() ?? '',
      assetId: json['asset_id']?.toString() ?? '',
      signalName: json['signal_name']?.toString() ?? '',
      category: json['category']?.toString(),
      value: json['value'],
      unit: json['unit']?.toString(),
      quality: json['quality']?.toString(),
      payload: json['payload'] is Map ? Map<String, dynamic>.from(json['payload'] as Map) : json,
    );
  }

  String get valueText {
    final raw = value == null ? '-' : value.toString();
    if (unit != null && unit!.isNotEmpty) return '$raw $unit';
    return raw;
  }
}
