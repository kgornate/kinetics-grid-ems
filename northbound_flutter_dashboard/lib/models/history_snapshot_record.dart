import 'telemetry_signal.dart';

class HistorySnapshotRecord {
  const HistorySnapshotRecord({
    required this.id,
    required this.timestampUtc,
    required this.assetId,
    required this.signals,
    required this.payload,
  });

  final int? id;
  final String timestampUtc;
  final String assetId;
  final Map<String, TelemetrySignal> signals;
  final Map<String, dynamic> payload;

  factory HistorySnapshotRecord.fromJson(Map<String, dynamic> json) {
    final payload = json['payload'] is Map ? Map<String, dynamic>.from(json['payload'] as Map) : <String, dynamic>{};
    final signalMapRaw = payload['signals'] ?? payload['key_signals'] ?? json['signals'] ?? json['key_signals'];
    final parsedSignals = <String, TelemetrySignal>{};

    if (signalMapRaw is Map) {
      for (final entry in signalMapRaw.entries) {
        final name = entry.key.toString();
        parsedSignals[name] = TelemetrySignal.fromEntry(name, entry.value);
      }
    }

    return HistorySnapshotRecord(
      id: json['id'] is int ? json['id'] as int : int.tryParse(json['id']?.toString() ?? ''),
      timestampUtc: json['timestamp_utc']?.toString() ?? payload['timestamp_utc']?.toString() ?? '',
      assetId: json['asset_id']?.toString() ?? payload['asset_id']?.toString() ?? '',
      signals: parsedSignals,
      payload: payload.isEmpty ? json : payload,
    );
  }

  TelemetrySignal? signal(String signalName) => signals[signalName];
}
