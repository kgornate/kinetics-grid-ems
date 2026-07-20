
import '../models/site_dashboard_summary.dart';
import '../models/source_home_summary.dart';
import '../models/source_summary.dart';

class DashboardAggregator {
  const DashboardAggregator._();

  static SiteDashboardSummary build({
    required Map<String, dynamic> health,
    required List<SourceSummary> sources,
    required Map<String, dynamic> keySignals,
    required int alarmCount,
  }) {
    final assets = (keySignals['assets'] as Map?)?.cast<String, dynamic>() ?? {};

    final sourceSummaries = sources.map((source) {
      final sourceAssets = _assetsForSource(assets, source.sourceId);
      final bessState = _deriveBessState(sourceAssets);
      return SourceHomeSummary(
        sourceId: source.sourceId,
        displayName: source.displayName,
        host: source.host,
        port: source.port,
        online: source.online,
        assetCount: source.assetCount,
        onlineAssetCount: source.onlineAssetCount,
        signalCount: source.signalCount,
        badSignalCount: source.badSignalCount,
        soc: _findPreferredSoc(sourceAssets),
        activePowerKw: _findPreferredSourcePower(sourceAssets),
        fireAlarmActive: _findBooleanLikeAlarm(
          sourceAssets,
          preferredAssetContains: const ['fire'],
          preferredSignalContains: const ['fire_alarm', 'alarm', 'fault'],
        ),
        pcsOnline: _assetOnlineRollup(sourceAssets, 'pcs'),
        bmsOnline: _assetOnlineRollup(sourceAssets, 'bms'),
        liquidCoolingOnline: _assetOnlineRollup(sourceAssets, 'liquid_cooling'),
        fireOnline: _assetOnlineRollup(sourceAssets, 'fire'),
        dehumidifierOnline: _assetOnlineRollup(sourceAssets, 'dehumidifier'),
        bessOn: bessState.isOn,
        bessStatusLabel: bessState.statusLabel,
        bessModeLabel: bessState.modeLabel,
        controlAuthorityLabel: bessState.controlAuthorityLabel,
      );
    }).toList();

    final socValues = sourceSummaries
        .map((e) => e.soc)
        .whereType<double>()
        .where((e) => e >= 0 && e <= 100)
        .toList();

    final powerValues = sourceSummaries
        .map((e) => e.activePowerKw)
        .whereType<double>()
        .toList();

    final knownBessStates = sourceSummaries.where((e) => e.bessOn != null).toList();

    return SiteDashboardSummary(
      sourceCount: (health['source_count'] as num?)?.toInt() ?? sources.length,
      onlineSourceCount: sources.where((e) => e.online).length,
      assetCount: (health['asset_count'] as num?)?.toInt() ?? 0,
      onlineAssetCount: (health['online_asset_count'] as num?)?.toInt() ?? 0,
      totalSignalCount: (health['total_signal_count'] as num?)?.toInt() ?? 0,
      badSignalCount: (health['bad_signal_count'] as num?)?.toInt() ?? 0,
      alarmCount: alarmCount,
      storageEnabled: (health['storage'] as Map?)?['enabled'] == true,
      gatewayMode: health['gateway_mode']?.toString() ?? 'unknown',
      commandsEnabled: health['commands_enabled'] == true,
      controlEnabled: health['control_enabled'] == true,
      overallSoc: socValues.isEmpty
          ? null
          : socValues.reduce((a, b) => a + b) / socValues.length,
      siteActivePowerKw: powerValues.isEmpty
          ? null
          : powerValues.reduce((a, b) => a + b),
      fireAlarmActive: sourceSummaries.any((e) => e.fireAlarmActive),
      sources: sourceSummaries,
      bessKnownCount: knownBessStates.length,
      bessOnCount: knownBessStates.where((e) => e.bessOn == true).length,
    );
  }

  static Map<String, dynamic> _assetsForSource(
    Map<String, dynamic> assets,
    String sourceId,
  ) {
    final result = <String, dynamic>{};
    for (final entry in assets.entries) {
      final key = entry.key.toLowerCase();
      final asset = (entry.value as Map?)?.cast<String, dynamic>() ?? const {};
      final assetSourceId = asset['source_id']?.toString();
      if (assetSourceId == sourceId || key.startsWith('${sourceId.toLowerCase()}_')) {
        result[entry.key] = asset;
      }
    }
    return result;
  }

  static bool _assetOnlineRollup(Map<String, dynamic> assets, String assetKey) {
    final matches = assets.entries
        .where((entry) => entry.key.toLowerCase().contains(assetKey.toLowerCase()))
        .map((entry) => (entry.value as Map?)?.cast<String, dynamic>() ?? const {})
        .toList();

    if (matches.isEmpty) return false;
    return matches.any((item) => item['online'] == true);
  }

  static double? _findPreferredSoc(Map<String, dynamic> assets) {
    const exactPriority = [
      'cluster_internal_soc',
      'soc',
      'battery_soc',
      'display_soc',
      'total_soc',
    ];

    for (final entry in assets.entries) {
      final assetKey = entry.key.toLowerCase();
      if (!assetKey.contains('bms') && !assetKey.contains('ems_system')) {
        continue;
      }

      final asset = (entry.value as Map?)?.cast<String, dynamic>() ?? const {};
      final keySignals = (asset['key_signals'] as Map?)?.cast<String, dynamic>() ?? {};

      for (final signalName in exactPriority) {
        if (keySignals.containsKey(signalName)) {
          final value = _extractNumericValue(keySignals[signalName]);
          if (value != null && value >= 0 && value <= 100) {
            return value;
          }
        }
      }
    }

    for (final entry in assets.entries) {
      final assetKey = entry.key.toLowerCase();
      if (!assetKey.contains('bms') && !assetKey.contains('ems_system')) {
        continue;
      }

      final asset = (entry.value as Map?)?.cast<String, dynamic>() ?? const {};
      final keySignals = (asset['key_signals'] as Map?)?.cast<String, dynamic>() ?? {};

      for (final signalEntry in keySignals.entries) {
        final key = signalEntry.key.toLowerCase();
        if (!key.contains('soc')) continue;
        if (key.contains('limit') ||
            key.contains('setting') ||
            key.contains('cutoff') ||
            key.contains('enable') ||
            key.contains('alarm') ||
            key.contains('fault') ||
            key.contains('dispatch')) {
          continue;
        }

        final value = _extractNumericValue(signalEntry.value);
        if (value != null && value >= 0 && value <= 100) {
          return value;
        }
      }
    }

    return null;
  }

  static double? _findPreferredSourcePower(Map<String, dynamic> assets) {
    const exactPriority = [
      'total_active_power',
      'active_power',
      'mains_current_total_power',
      'grid_current_total_power',
      'metering_current_total_power',
      'load_power',
    ];

    final orderedAssets = assets.entries.toList()
      ..sort((a, b) {
        final ak = a.key.toLowerCase();
        final bk = b.key.toLowerCase();
        int rank(String k) {
          if (k.contains('pcs')) return 0;
          if (k.contains('utility_meter') || k.contains('grid_meter')) return 1;
          if (k.contains('ems_system')) return 2;
          return 3;
        }
        return rank(ak).compareTo(rank(bk));
      });

    for (final entry in orderedAssets) {
      final asset = (entry.value as Map?)?.cast<String, dynamic>() ?? const {};
      final keySignals = (asset['key_signals'] as Map?)?.cast<String, dynamic>() ?? {};

      for (final signalName in exactPriority) {
        if (keySignals.containsKey(signalName)) {
          final value = _extractNumericValue(keySignals[signalName]);
          if (value != null) return value;
        }
      }
    }

    return null;
  }

  static _BessState _deriveBessState(Map<String, dynamic> assets) {
    final keySignals = _mergedControlSignals(assets);

    final manualAutoMode = _findSignalValue(keySignals, const [
      'manual_auto_mode',
      'remote_mode',
    ]);

    final modeCode = _findSignalValue(keySignals, const [
      'manual_mode_control',
      'remote_control_mode',
      'charge_discharge_control_mode',
      'auto_mode_control',
      'master_control_mode',
    ]);

    final powerOnCode = _findSignalValue(keySignals, const [
      'power_on_command',
      'manual_power_on',
      'auto_power_on',
      'pcs_power_on_off_control',
      'bms_power_on_off_control',
    ]);

    final activePower = _findPreferredSourcePower(assets);

    final modeLabel = _mapModeLabel(modeCode, activePower: activePower, powerOnCode: powerOnCode);
    final status = _mapBessOnOff(modeCode, powerOnCode: powerOnCode, activePower: activePower);

    return _BessState(
      isOn: status,
      statusLabel: status == null ? 'UNKNOWN' : (status ? 'ON' : 'OFF'),
      modeLabel: modeLabel,
      controlAuthorityLabel: manualAutoMode == null
          ? 'Unknown control'
          : (manualAutoMode.round() == 0 ? 'Manual control' : 'Auto control'),
    );
  }

  static Map<String, dynamic> _mergedControlSignals(Map<String, dynamic> assets) {
    final result = <String, dynamic>{};
    final preferredEntries = assets.entries.toList()
      ..sort((a, b) {
        int rank(String key) {
          final k = key.toLowerCase();
          if (k.contains('ems_system')) return 0;
          if (k.contains('remote_control')) return 1;
          return 2;
        }
        return rank(a.key).compareTo(rank(b.key));
      });

    for (final entry in preferredEntries) {
      final asset = (entry.value as Map?)?.cast<String, dynamic>() ?? const {};
      final keySignals = (asset['key_signals'] as Map?)?.cast<String, dynamic>() ?? {};
      for (final signal in keySignals.entries) {
        result.putIfAbsent(signal.key, () => signal.value);
      }
    }
    return result;
  }

  static double? _findSignalValue(Map<String, dynamic> keySignals, List<String> names) {
    for (final name in names) {
      if (keySignals.containsKey(name)) {
        final value = _extractNumericValue(keySignals[name]);
        if (value != null) return value;
      }
    }
    return null;
  }

  static String _mapModeLabel(double? modeCode, {double? activePower, double? powerOnCode}) {
    final code = modeCode?.round();
    switch (code) {
      case 1:
        return 'Shutdown';
      case 2:
        return 'Standby';
      case 3:
        return 'Charging';
      case 4:
        return 'Discharging';
    }

    if (activePower != null) {
      if (activePower > 0.3) return 'Discharging';
      if (activePower < -0.3) return 'Charging';
    }

    if (powerOnCode != null && powerOnCode.round() == 1) {
      return 'Standby';
    }

    return 'Unknown';
  }

  static bool? _mapBessOnOff(double? modeCode, {double? powerOnCode, double? activePower}) {
    final code = modeCode?.round();
    if (code == 1) return false;
    if (code == 2 || code == 3 || code == 4) return true;

    if (powerOnCode != null) {
      final p = powerOnCode.round();
      if (p == 0) return false;
      if (p == 1) return true;
    }

    if (activePower != null && activePower.abs() > 0.3) {
      return true;
    }

    return null;
  }

  static bool _findBooleanLikeAlarm(
    Map<String, dynamic> assets, {
    required List<String> preferredAssetContains,
    required List<String> preferredSignalContains,
  }) {
    for (final entry in assets.entries) {
      final assetKey = entry.key.toLowerCase();
      if (!preferredAssetContains.any((part) => assetKey.contains(part))) {
        continue;
      }

      final asset = (entry.value as Map?)?.cast<String, dynamic>() ?? const {};
      final keySignals = (asset['key_signals'] as Map?)?.cast<String, dynamic>() ?? {};

      for (final signalEntry in keySignals.entries) {
        final key = signalEntry.key.toLowerCase();
        if (!preferredSignalContains.any((part) => key.contains(part))) {
          continue;
        }
        final value = _extractNumericValue(signalEntry.value);
        if (value != null && value > 0) return true;
      }
    }
    return false;
  }

  static double? _extractNumericValue(dynamic signalValue) {
    if (signalValue is num) return signalValue.toDouble();

    if (signalValue is Map<String, dynamic>) {
      final value = signalValue['value'];
      if (value is num) return value.toDouble();
      if (value is String) return double.tryParse(value);
    }

    return null;
  }
}

class _BessState {
  const _BessState({
    required this.isOn,
    required this.statusLabel,
    required this.modeLabel,
    required this.controlAuthorityLabel,
  });

  final bool? isOn;
  final String statusLabel;
  final String modeLabel;
  final String controlAuthorityLabel;
}
