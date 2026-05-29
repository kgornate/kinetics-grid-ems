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
    this.igbtTemperatureC,
    this.ambientTemperatureC,
    this.inductanceTemperatureC,
    required this.receivedAt,
  });

  factory PcsTelemetry.fromJson(Map<String, dynamic> json) {
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
      faultStatus: _toBool(json['fault_status']),
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

  bool get isOnline => commStatus?.toLowerCase() == 'online';

  bool get isRunning {
    final status = operatingStatus?.toLowerCase() ?? '';
    return status.contains('running') || status.contains('operation');
  }
}
