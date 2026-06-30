import '../models/signal_preview.dart';

class KeySignalParser {
  const KeySignalParser._();

  static Map<String, List<SignalPreview>> byAsset(Map<String, dynamic>? payload) {
    if (payload == null || payload.isEmpty) return const {};
    final result = <String, List<SignalPreview>>{};

    final assets = payload['assets'];
    if (assets is Map) {
      for (final entry in assets.entries) {
        final assetId = entry.key.toString();
        final signals = _extractSignalsFromAny(entry.value);
        if (signals.isNotEmpty) result[assetId] = signals;
      }
    } else if (assets is List) {
      for (final item in assets) {
        if (item is! Map) continue;
        final map = Map<String, dynamic>.from(item);
        final assetId = (map['asset_id'] ?? map['id'])?.toString();
        if (assetId == null || assetId.isEmpty) continue;
        final signals = _extractSignalsFromAny(map);
        if (signals.isNotEmpty) result[assetId] = signals;
      }
    }

    if (result.isEmpty) {
      for (final entry in payload.entries) {
        final key = entry.key;
        if (_reservedTopLevelKeys.contains(key)) continue;
        final signals = _extractSignalsFromAny(entry.value);
        if (signals.isNotEmpty) result[key] = signals;
      }
    }

    return result;
  }

  static List<SignalPreview> _extractSignalsFromAny(dynamic raw) {
    if (raw is! Map) return const [];
    final map = Map<String, dynamic>.from(raw);
    final candidate = map['key_signals'] ?? map['signals'] ?? map['telemetry'] ?? map['data'] ?? map;
    if (candidate is! Map) return const [];

    final signals = <SignalPreview>[];
    for (final entry in candidate.entries) {
      final key = entry.key.toString();
      if (_reservedSignalKeys.contains(key)) continue;
      signals.add(SignalPreview.fromEntry(key, entry.value));
    }
    signals.sort((a, b) => _priorityScore(a.name).compareTo(_priorityScore(b.name)));
    return signals;
  }

  static const _reservedTopLevelKeys = {
    'status',
    'gateway',
    'gateway_id',
    'gateway_mode',
    'timestamp_utc',
    'timestamp',
    'health',
    'alarms',
    'schema_version',
    'network',
    'mode',
  };

  static const _reservedSignalKeys = {
    'asset_id',
    'display_name',
    'online',
    'last_update_utc',
    'signal_count',
    'good_signal_count',
    'bad_signal_count',
  };

  static int _priorityScore(String name) {
    final n = name.toLowerCase();
    if (n.contains('soc')) return 0;
    if (n.contains('soh')) return 1;
    if (n.contains('active_power') || n.contains('power_kw')) return 2;
    if (n.contains('dc_power')) return 3;
    if (n.contains('voltage')) return 4;
    if (n.contains('current')) return 5;
    if (n.contains('frequency')) return 6;
    if (n.contains('temperature') || n.contains('temp')) return 7;
    if (n.contains('insulation')) return 8;
    if (n.contains('status')) return 9;
    if (n.contains('alarm') || n.contains('fault')) return 10;
    return 100;
  }
}
