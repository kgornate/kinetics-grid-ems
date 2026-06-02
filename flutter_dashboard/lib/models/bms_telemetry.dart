class BmsTelemetry {
  final String? assetId;
  final String? communicationStatus;
  final String? commStatus;
  final String? lastUpdateTs;
  final String? error;

  final double? socPercent;
  final double? sohPercent;
  final double? rackInnerSocPercent;

  final double? rackVoltageV;
  final double? rackCurrentA;
  final double? powerKw;

  final double? maxAllowedChargeCurrentA;
  final double? maxAllowedDischargeCurrentA;

  final double? maxCellVoltageMv;
  final double? minCellVoltageMv;
  final double? avgCellVoltageMv;
  final double? cellVoltageDiffMv;

  final double? maxCellTempC;
  final double? minCellTempC;
  final double? avgTempC;
  final double? maxTempDiffC;

  final double? insulationResistanceKohm;
  final double? positiveInsulationResistanceKohm;
  final double? negativeInsulationResistanceKohm;

  final String? prechargeStage;
  final String? bcuState;
  final String? currentState;
  final int? heartbeat;

  final bool positiveContactorClosed;
  final bool prechargeContactorClosed;
  final bool negativeContactorClosed;
  final List<String> contactorActiveFlags;

  final List<String> activeAlarms;
  final int alarmCount;

  final Map<String, dynamic> raw;
  final DateTime receivedAt;

  BmsTelemetry({
    this.assetId,
    this.communicationStatus,
    this.commStatus,
    this.lastUpdateTs,
    this.error,
    this.socPercent,
    this.sohPercent,
    this.rackInnerSocPercent,
    this.rackVoltageV,
    this.rackCurrentA,
    this.powerKw,
    this.maxAllowedChargeCurrentA,
    this.maxAllowedDischargeCurrentA,
    this.maxCellVoltageMv,
    this.minCellVoltageMv,
    this.avgCellVoltageMv,
    this.cellVoltageDiffMv,
    this.maxCellTempC,
    this.minCellTempC,
    this.avgTempC,
    this.maxTempDiffC,
    this.insulationResistanceKohm,
    this.positiveInsulationResistanceKohm,
    this.negativeInsulationResistanceKohm,
    this.prechargeStage,
    this.bcuState,
    this.currentState,
    this.heartbeat,
    this.positiveContactorClosed = false,
    this.prechargeContactorClosed = false,
    this.negativeContactorClosed = false,
    this.contactorActiveFlags = const [],
    this.activeAlarms = const [],
    this.alarmCount = 0,
    required this.raw,
    required this.receivedAt,
  });

  factory BmsTelemetry.fromJson(Map<String, dynamic> json) {
    final data = _extractBmsData(json);
    final alarms = _toStringList(
      data['active_alarms'] ?? data['alarms'] ?? data['active_alarm_list'],
    );

    final explicitAlarmCount = _toInt(data['alarm_count']);

    return BmsTelemetry(
      assetId: data['asset_id']?.toString(),
      communicationStatus: data['communication_status']?.toString(),
      commStatus: data['comm_status']?.toString(),
      lastUpdateTs: data['last_update_ts']?.toString() ?? data['timestamp']?.toString(),
      error: data['error']?.toString(),
      socPercent: _toDouble(data['soc_percent'] ?? data['soc']),
      sohPercent: _toDouble(data['soh_percent'] ?? data['soh']),
      rackInnerSocPercent: _toDouble(data['rack_inner_soc_percent']),
      rackVoltageV: _toDouble(data['rack_voltage_v'] ?? data['total_voltage_v']),
      rackCurrentA: _toDouble(data['rack_current_a'] ?? data['total_current_a']),
      powerKw: _toDouble(data['power_kw']),
      maxAllowedChargeCurrentA: _toDouble(
        data['max_allowed_charge_current_a'] ?? data['available_charge_current_a'],
      ),
      maxAllowedDischargeCurrentA: _toDouble(
        data['max_allowed_discharge_current_a'] ?? data['available_discharge_current_a'],
      ),
      maxCellVoltageMv: _toDouble(data['max_cell_voltage_mv']),
      minCellVoltageMv: _toDouble(data['min_cell_voltage_mv']),
      avgCellVoltageMv: _toDouble(data['avg_cell_voltage_mv']),
      cellVoltageDiffMv: _toDouble(data['cell_voltage_diff_mv']),
      maxCellTempC: _toDouble(data['max_cell_temp_c']),
      minCellTempC: _toDouble(data['min_cell_temp_c']),
      avgTempC: _toDouble(data['avg_temp_c'] ?? data['avg_cell_temp_c']),
      maxTempDiffC: _toDouble(data['max_temp_diff_c']),
      insulationResistanceKohm: _toDouble(data['insulation_resistance_kohm']),
      positiveInsulationResistanceKohm: _toDouble(
        data['positive_insulation_resistance_kohm'] ?? data['positive_insulation_kohm'],
      ),
      negativeInsulationResistanceKohm: _toDouble(
        data['negative_insulation_resistance_kohm'] ?? data['negative_insulation_kohm'],
      ),
      prechargeStage: data['precharge_stage']?.toString() ?? data['precharge_status']?.toString(),
      bcuState: data['bcu_state']?.toString(),
      currentState: data['current_state']?.toString(),
      heartbeat: _toInt(data['heartbeat']),
      positiveContactorClosed: _toBool(data['positive_contactor_closed']),
      prechargeContactorClosed: _toBool(data['precharge_contactor_closed']),
      negativeContactorClosed: _toBool(data['negative_contactor_closed']),
      contactorActiveFlags: _toStringList(data['contactor_active_flags']),
      activeAlarms: alarms,
      alarmCount: explicitAlarmCount ?? alarms.length,
      raw: Map<String, dynamic>.from(data),
      receivedAt: DateTime.now(),
    );
  }

  static Map<String, dynamic> _extractBmsData(Map<String, dynamic> json) {
    final directData = _asMap(json['data']);
    if (_looksLikeBms(directData)) return directData;

    final directBms = _asMap(json['bms']);
    if (directBms.isNotEmpty) return directBms;

    final assets = _asMap(json['assets']);
    final assetsBms = _asMap(assets['bms']);
    if (assetsBms.isNotEmpty) return assetsBms;

    final payload = _asMap(json['payload']);
    if (payload.isNotEmpty) {
      final payloadBms = _asMap(payload['bms']);
      if (payloadBms.isNotEmpty) return payloadBms;

      final payloadAssets = _asMap(payload['assets']);
      final payloadAssetsBms = _asMap(payloadAssets['bms']);
      if (payloadAssetsBms.isNotEmpty) return payloadAssetsBms;

      final payloadData = _asMap(payload['data']);
      if (_looksLikeBms(payloadData)) return payloadData;
    }

    return json;
  }

  static bool _looksLikeBms(Map<String, dynamic> data) {
    if (data.isEmpty) return false;
    return data.containsKey('soc_percent') ||
        data.containsKey('rack_voltage_v') ||
        data.containsKey('max_cell_voltage_mv') ||
        data.containsKey('insulation_resistance_kohm') ||
        data['asset_id']?.toString() == 'bms_1';
  }

  static Map<String, dynamic> _asMap(dynamic value) {
    if (value is Map<String, dynamic>) return value;
    if (value is Map) return Map<String, dynamic>.from(value);
    return {};
  }

  static double? _toDouble(dynamic value) {
    if (value == null) return null;
    if (value is num) return value.toDouble();
    final text = value.toString().trim();
    if (text.isEmpty) return null;
    return double.tryParse(text);
  }

  static int? _toInt(dynamic value) {
    if (value == null) return null;
    if (value is int) return value;
    if (value is num) return value.toInt();
    final text = value.toString().trim();
    if (text.isEmpty) return null;
    return int.tryParse(text);
  }

  static bool _toBool(dynamic value) {
    if (value == null) return false;
    if (value is bool) return value;
    if (value is num) return value != 0;
    final text = value.toString().toLowerCase().trim();
    return text == 'true' || text == '1' || text == 'yes' || text == 'closed' || text == 'online';
  }

  static List<String> _toStringList(dynamic value) {
    if (value == null) return const [];
    if (value is List) {
      return value.map((item) => item.toString()).where((item) => item.trim().isNotEmpty).toList();
    }
    final text = value.toString().trim();
    if (text.isEmpty) return const [];
    return text.split(',').map((item) => item.trim()).where((item) => item.isNotEmpty).toList();
  }

  String get effectiveCommStatus {
    return communicationStatus ?? commStatus ?? (error == null ? 'online' : 'offline');
  }

  bool get isOnline {
    final status = effectiveCommStatus.toLowerCase();
    return status == 'online' || status == 'ok' || status == 'connected';
  }

  bool get hasAlarms => alarmCount > 0 || activeAlarms.isNotEmpty;

  bool get allMainContactorsClosed {
    return positiveContactorClosed && negativeContactorClosed;
  }
}
