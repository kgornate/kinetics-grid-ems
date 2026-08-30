class ControllerBessStatus {
  final String host;
  final double? socPercent;
  final bool online;
  final String targetState;

  const ControllerBessStatus({
    required this.host,
    required this.socPercent,
    required this.online,
    required this.targetState,
  });

  factory ControllerBessStatus.fromJson(Map<String, dynamic> json) {
    return ControllerBessStatus(
      host: json['host']?.toString() ?? '',
      socPercent: _asDouble(json['soc_percent']),
      online: json['online'] == true,
      targetState: json['target_state']?.toString() ?? '--',
    );
  }
}

class SolisOperatorStatus {
  final bool enabled;
  final bool online;
  final String state;
  final String targetState;
  final double? activePowerKw;
  final int? activePowerW;
  final String serialPort;
  final int? unitId;

  const SolisOperatorStatus({
    required this.enabled,
    required this.online,
    required this.state,
    required this.targetState,
    required this.activePowerKw,
    required this.activePowerW,
    required this.serialPort,
    required this.unitId,
  });

  factory SolisOperatorStatus.fromJson(Map<String, dynamic> json) {
    return SolisOperatorStatus(
      enabled: json['enabled'] != false,
      online: json['online'] == true,
      state: json['state']?.toString() ?? 'UNKNOWN',
      targetState: json['target_state']?.toString() ?? '--',
      activePowerKw: _asDouble(json['active_power_kw']),
      activePowerW: _asInt(json['active_power_w']),
      serialPort: json['serial_port']?.toString() ?? '',
      unitId: _asInt(json['unit_id']),
    );
  }
}

class ControllerThresholds {
  final double? highSocPercent;
  final double? recoverySocPercent;
  final bool lowCutoffEnabled;
  final double? lowCutoffPercent;
  final double? lowRecoveryPercent;
  final int? settingsRevision;
  final String updatedAtUtc;
  final String updatedBy;

  const ControllerThresholds({
    required this.highSocPercent,
    required this.recoverySocPercent,
    required this.lowCutoffEnabled,
    required this.lowCutoffPercent,
    required this.lowRecoveryPercent,
    required this.settingsRevision,
    required this.updatedAtUtc,
    required this.updatedBy,
  });

  factory ControllerThresholds.fromJson(Map<String, dynamic> json) {
    return ControllerThresholds(
      highSocPercent: _asDouble(json['high_soc_percent']),
      recoverySocPercent: _asDouble(json['recovery_soc_percent']),
      lowCutoffEnabled: json['low_cutoff_enabled'] == true,
      lowCutoffPercent: _asDouble(json['low_cutoff_percent']),
      lowRecoveryPercent: _asDouble(json['low_recovery_percent']),
      settingsRevision: _asInt(json['settings_revision']),
      updatedAtUtc: json['settings_updated_at_utc']?.toString() ?? '',
      updatedBy: json['settings_updated_by']?.toString() ?? '',
    );
  }
}

class ControllerOperatorStatus {
  final bool available;
  final bool healthy;
  final String timestampUtc;
  final String version;
  final String mode;
  final String state;
  final String previousState;
  final String decision;
  final String? error;
  final ControllerThresholds thresholds;
  final ControllerBessStatus bessX;
  final ControllerBessStatus bessY;
  final SolisOperatorStatus solis;

  const ControllerOperatorStatus({
    required this.available,
    required this.healthy,
    required this.timestampUtc,
    required this.version,
    required this.mode,
    required this.state,
    required this.previousState,
    required this.decision,
    required this.error,
    required this.thresholds,
    required this.bessX,
    required this.bessY,
    required this.solis,
  });

  factory ControllerOperatorStatus.fromJson(Map<String, dynamic> json) {
    final controller = _asMap(json['controller']);
    final bess = _asMap(json['bess']);
    return ControllerOperatorStatus(
      available: json['available'] != false,
      healthy: json['healthy'] == true,
      timestampUtc: json['timestamp_utc']?.toString() ?? '',
      version: json['version']?.toString() ?? '',
      mode: json['mode']?.toString() ?? '--',
      state: controller['state']?.toString() ?? 'UNKNOWN',
      previousState: controller['previous_state']?.toString() ?? '',
      decision: controller['decision']?.toString() ?? '',
      error: json['error']?.toString(),
      thresholds: ControllerThresholds.fromJson(_asMap(json['thresholds'])),
      bessX: ControllerBessStatus.fromJson(_asMap(bess['X'])),
      bessY: ControllerBessStatus.fromJson(_asMap(bess['Y'])),
      solis: SolisOperatorStatus.fromJson(_asMap(json['solis'])),
    );
  }
}

class ControllerSettingsSnapshot {
  final bool available;
  final int revision;
  final String updatedAtUtc;
  final String updatedBy;
  final double highLimit;
  final double recoveryLimit;
  final double lowCutoffLimit;
  final double lowRecoveryLimit;
  final bool lowCutoffEnabled;
  final String writeRole;
  final String runtimeReload;

  const ControllerSettingsSnapshot({
    required this.available,
    required this.revision,
    required this.updatedAtUtc,
    required this.updatedBy,
    required this.highLimit,
    required this.recoveryLimit,
    required this.lowCutoffLimit,
    required this.lowRecoveryLimit,
    required this.lowCutoffEnabled,
    required this.writeRole,
    required this.runtimeReload,
  });

  factory ControllerSettingsSnapshot.fromJson(Map<String, dynamic> json) {
    final settings = _asMap(json['settings']);
    return ControllerSettingsSnapshot(
      available: json['available'] != false,
      revision: _asInt(json['revision']) ?? 0,
      updatedAtUtc: json['updated_at_utc']?.toString() ?? '',
      updatedBy: json['updated_by']?.toString() ?? '',
      highLimit: _asDouble(settings['high_limit']) ?? 0,
      recoveryLimit: _asDouble(settings['recovery_limit']) ?? 0,
      lowCutoffLimit: _asDouble(settings['low_cutoff_limit']) ?? 0,
      lowRecoveryLimit: _asDouble(settings['low_recovery_limit']) ?? 0,
      lowCutoffEnabled: json['low_cutoff_enabled'] == true,
      writeRole: json['write_role']?.toString() ?? 'internal_admin',
      runtimeReload: json['runtime_reload']?.toString() ?? '',
    );
  }
}

class ControllerHistoryEvent {
  final int id;
  final String timestampUtc;
  final String severity;
  final String eventType;
  final String device;
  final String controllerState;
  final String decision;
  final double? socX;
  final double? socY;
  final String solisState;
  final double? solisPowerKw;
  final String target;
  final String result;
  final String message;
  final Map<String, dynamic> payload;

  const ControllerHistoryEvent({
    required this.id,
    required this.timestampUtc,
    required this.severity,
    required this.eventType,
    required this.device,
    required this.controllerState,
    required this.decision,
    required this.socX,
    required this.socY,
    required this.solisState,
    required this.solisPowerKw,
    required this.target,
    required this.result,
    required this.message,
    required this.payload,
  });

  factory ControllerHistoryEvent.fromJson(Map<String, dynamic> json) {
    final watts = _asDouble(json['solis_power_w']);
    return ControllerHistoryEvent(
      id: _asInt(json['id']) ?? 0,
      timestampUtc: json['timestamp_utc']?.toString() ?? '',
      severity: json['severity']?.toString() ?? 'info',
      eventType: json['event_type']?.toString() ?? '',
      device: json['device']?.toString() ?? '',
      controllerState: json['controller_state']?.toString() ?? '',
      decision: json['decision']?.toString() ?? '',
      socX: _asDouble(json['soc_x']),
      socY: _asDouble(json['soc_y']),
      solisState: json['solis_state']?.toString() ?? '',
      solisPowerKw: watts == null ? null : watts / 1000.0,
      target: json['target']?.toString() ?? '',
      result: json['result']?.toString() ?? '',
      message: json['message']?.toString() ?? '',
      payload: _asMap(json['payload']),
    );
  }
}

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return value.cast<String, dynamic>();
  return const <String, dynamic>{};
}

double? _asDouble(dynamic value) {
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString() ?? '');
}

int? _asInt(dynamic value) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '');
}
