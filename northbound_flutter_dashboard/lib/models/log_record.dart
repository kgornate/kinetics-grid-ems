class LogRecord {
  const LogRecord({
    required this.id,
    required this.timestampUtc,
    required this.severity,
    required this.eventType,
    required this.message,
    this.source,
    this.assetId,
    this.payload = const {},
  });

  final int id;
  final String timestampUtc;
  final String severity;
  final String eventType;
  final String message;
  final String? source;
  final String? assetId;
  final Map<String, dynamic> payload;

  factory LogRecord.fromJson(Map<String, dynamic> json) {
    return LogRecord(
      id: _asInt(json['id']),
      timestampUtc: json['timestamp_utc']?.toString() ?? json['timestamp']?.toString() ?? '',
      severity: json['severity']?.toString() ?? 'info',
      eventType: json['event_type']?.toString() ?? 'event',
      source: json['source']?.toString(),
      assetId: json['asset_id']?.toString(),
      message: json['message']?.toString() ?? '',
      payload: json['payload'] is Map ? Map<String, dynamic>.from(json['payload'] as Map) : const {},
    );
  }

  bool get isWarningOrError {
    final s = severity.toLowerCase();
    return s == 'warning' || s == 'error' || s == 'critical' || s == 'fault';
  }

  static int _asInt(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '') ?? 0;
  }
}
