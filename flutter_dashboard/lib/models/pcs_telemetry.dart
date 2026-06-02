class PcsTelemetry {
  final String? assetId;
  final String? vendor;
  final String? commStatus;
  final String? lastUpdateTs;
  final String? error;

  final double? abVoltageV;
  final double? bcVoltageV;
  final double? caVoltageV;

  final double? phaseAVoltageV;
  final double? phaseBVoltageV;
  final double? phaseCVoltageV;

  final double? phaseACurrentA;
  final double? phaseBCurrentA;
  final double? phaseCCurrentA;

  final double? frequencyHz;

  final double? activePowerKw;
  final double? reactivePowerKvar;
  final double? apparentPowerKva;
  final double? powerFactor;

  final double? busVoltageV;
  final double? batteryVoltageV;
  final double? batteryCurrentA;
  final double? dcPowerKw;
  final double? dcTotalCurrentA;

  final int? operatingStatusRaw;
  final String? operatingStatus;

  final int? gridOffgridStatusRaw;
  final String? gridOffgridStatus;

  final bool faultStatus;

  // Detailed NJOY/Enjoy fault words 0x1700..0x1707 from i.MX93 backend.
  final int? hardwareFaultWord1Raw;
  final int? hardwareFaultWord2Raw;
  final int? gridFaultWordRaw;
  final int? busFaultWordRaw;
  final int? acCapacitorFaultWordRaw;
  final int? systemFaultWordRaw;
  final int? switchFaultWordRaw;
  final int? otherFaultWordRaw;

  final Map<String, dynamic> faultWordsRaw;
  final Map<String, List<String>> faultCategories;
  final List<String> activeFaults;
  final int faultCount;
  final bool detailedFaultStatus;
  final String? faultWordsReadError;

  final double? igbtTemperatureC;
  final double? ambientTemperatureC;
  final double? inductanceTemperatureC;

  final DateTime receivedAt;

  PcsTelemetry({
    this.assetId,
    this.vendor,
    this.commStatus,
    this.lastUpdateTs,
    this.error,
    this.abVoltageV,
    this.bcVoltageV,
    this.caVoltageV,
    this.phaseAVoltageV,
    this.phaseBVoltageV,
    this.phaseCVoltageV,
    this.phaseACurrentA,
    this.phaseBCurrentA,
    this.phaseCCurrentA,
    this.frequencyHz,
    this.activePowerKw,
    this.reactivePowerKvar,
    this.apparentPowerKva,
    this.powerFactor,
    this.busVoltageV,
    this.batteryVoltageV,
    this.batteryCurrentA,
    this.dcPowerKw,
    this.dcTotalCurrentA,
    this.operatingStatusRaw,
    this.operatingStatus,
    this.gridOffgridStatusRaw,
    this.gridOffgridStatus,
    this.faultStatus = false,
    this.hardwareFaultWord1Raw,
    this.hardwareFaultWord2Raw,
    this.gridFaultWordRaw,
    this.busFaultWordRaw,
    this.acCapacitorFaultWordRaw,
    this.systemFaultWordRaw,
    this.switchFaultWordRaw,
    this.otherFaultWordRaw,
    this.faultWordsRaw = const {},
    this.faultCategories = const {},
    this.activeFaults = const [],
    this.faultCount = 0,
    this.detailedFaultStatus = false,
    this.faultWordsReadError,
    this.igbtTemperatureC,
    this.ambientTemperatureC,
    this.inductanceTemperatureC,
    required this.receivedAt,
  });

  factory PcsTelemetry.fromJson(Map<String, dynamic> json) {
    final activeFaults = _toStringList(json['active_faults']);
    final faultCategories = _toFaultCategories(json['fault_categories']);
    final faultWordsRaw = _toStringDynamicMap(json['fault_words_raw']);
    final faultCount = _toInt(json['fault_count']) ?? activeFaults.length;
    final detailedFaultStatus = _toBool(json['detailed_fault_status']) ||
        activeFaults.isNotEmpty ||
        faultCount > 0;
    final faultStatus = _toBool(json['fault_status']) || detailedFaultStatus;

    return PcsTelemetry(
      assetId: json['asset_id']?.toString(),
      vendor: json['vendor']?.toString(),
      commStatus: json['comm_status']?.toString(),
      lastUpdateTs: json['last_update_ts']?.toString(),
      error: json['error']?.toString(),
      abVoltageV: _toDouble(json['ab_voltage_v']),
      bcVoltageV: _toDouble(json['bc_voltage_v']),
      caVoltageV: _toDouble(json['ca_voltage_v']),
      phaseAVoltageV: _toDouble(json['phase_a_voltage_v']),
      phaseBVoltageV: _toDouble(json['phase_b_voltage_v']),
      phaseCVoltageV: _toDouble(json['phase_c_voltage_v']),
      phaseACurrentA: _toDouble(json['phase_a_current_a']),
      phaseBCurrentA: _toDouble(json['phase_b_current_a']),
      phaseCCurrentA: _toDouble(json['phase_c_current_a']),
      frequencyHz: _toDouble(json['frequency_hz']),
      activePowerKw: _toDouble(json['active_power_kw']),
      reactivePowerKvar: _toDouble(json['reactive_power_kvar']),
      apparentPowerKva: _toDouble(json['apparent_power_kva']),
      powerFactor: _toDouble(json['power_factor']),
      busVoltageV: _toDouble(json['bus_voltage_v']),
      batteryVoltageV: _toDouble(json['battery_voltage_v']),
      batteryCurrentA: _toDouble(json['battery_current_a']),
      dcPowerKw: _toDouble(json['dc_power_kw']),
      dcTotalCurrentA: _toDouble(json['dc_total_current_a']),
      operatingStatusRaw: _toInt(json['operating_status_raw']),
      operatingStatus: json['operating_status']?.toString(),
      gridOffgridStatusRaw: _toInt(json['grid_offgrid_status_raw']),
      gridOffgridStatus: json['grid_offgrid_status']?.toString(),
      faultStatus: faultStatus,
      hardwareFaultWord1Raw: _toInt(json['hardware_fault_word_1_raw']),
      hardwareFaultWord2Raw: _toInt(json['hardware_fault_word_2_raw']),
      gridFaultWordRaw: _toInt(json['grid_fault_word_raw']),
      busFaultWordRaw: _toInt(json['bus_fault_word_raw']),
      acCapacitorFaultWordRaw: _toInt(json['ac_capacitor_fault_word_raw']),
      systemFaultWordRaw: _toInt(json['system_fault_word_raw']),
      switchFaultWordRaw: _toInt(json['switch_fault_word_raw']),
      otherFaultWordRaw: _toInt(json['other_fault_word_raw']),
      faultWordsRaw: faultWordsRaw,
      faultCategories: faultCategories,
      activeFaults: activeFaults,
      faultCount: faultCount,
      detailedFaultStatus: detailedFaultStatus,
      faultWordsReadError: json['fault_words_read_error']?.toString(),
      igbtTemperatureC: _toDouble(json['igbt_temperature_c']),
      ambientTemperatureC: _toDouble(json['ambient_temperature_c']),
      inductanceTemperatureC: _toDouble(json['inductance_temperature_c']),
      receivedAt: DateTime.now(),
    );
  }

  static double? _toDouble(dynamic value) {
    if (value == null) return null;
    if (value is num) return value.toDouble();
    return double.tryParse(value.toString());
  }

  static int? _toInt(dynamic value) {
    if (value == null) return null;
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value.toString());
  }

  static bool _toBool(dynamic value) {
    if (value == null) return false;
    if (value is bool) return value;
    if (value is num) return value != 0;
    final text = value.toString().toLowerCase().trim();
    return text == 'true' || text == '1' || text == 'yes' || text == 'fault';
  }

  static List<String> _toStringList(dynamic value) {
    if (value == null) return const [];
    if (value is List) {
      return value.map((item) => item.toString()).where((item) => item.isNotEmpty).toList();
    }
    final text = value.toString().trim();
    if (text.isEmpty) return const [];
    return text
        .split(';')
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .toList();
  }

  static Map<String, dynamic> _toStringDynamicMap(dynamic value) {
    if (value is Map<String, dynamic>) return value;
    if (value is Map) return Map<String, dynamic>.from(value);
    return const {};
  }

  static Map<String, List<String>> _toFaultCategories(dynamic value) {
    final map = _toStringDynamicMap(value);
    if (map.isEmpty) return const {};

    final parsed = <String, List<String>>{};
    map.forEach((key, rawValue) {
      parsed[key.toString()] = _toStringList(rawValue);
    });
    return parsed;
  }

  bool get isOnline => commStatus?.toLowerCase() == 'online';

  bool get isRunning {
    final status = operatingStatus?.toLowerCase() ?? '';
    return status.contains('running') || status.contains('operation');
  }

  bool get hasDetailedFault =>
      detailedFaultStatus || faultCount > 0 || activeFaults.isNotEmpty;

  bool get hasAnyFault => faultStatus || hasDetailedFault;
}
