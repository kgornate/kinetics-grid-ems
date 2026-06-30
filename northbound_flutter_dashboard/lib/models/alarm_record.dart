class AlarmRecord {
  AlarmRecord({
    required this.alarmId,
    required this.severity,
    required this.assetId,
    required this.message,
    required this.timestampUtc,
    this.sourceSignal,
  });

  final String alarmId;
  final String severity;
  final String assetId;
  final String message;
  final String timestampUtc;
  final String? sourceSignal;

  factory AlarmRecord.fromJson(Map<String, dynamic> json) {
    return AlarmRecord(
      alarmId: json['alarm_id']?.toString() ?? json['id']?.toString() ?? 'alarm',
      severity: json['severity']?.toString() ?? 'info',
      assetId: json['asset_id']?.toString() ?? 'unknown',
      message: json['message']?.toString() ?? json['description']?.toString() ?? '',
      timestampUtc: json['timestamp_utc']?.toString() ?? json['timestamp']?.toString() ?? '',
      sourceSignal: json['source_signal']?.toString(),
    );
  }
}
