class ChillerTelemetry {
  final String? waterPump;
  final String? compressor1;
  final String? compressor2;
  final String? electricHeater;
  final String? condensateFan;
  final String? makeupPump;

  final double? outletWaterTemp;
  final double? returnWaterTemp;
  final double? outletWaterPressure;
  final double? returnWaterPressure;
  final double? ambientTemp;

  final dynamic faultCode;
  final dynamic controlMode;
  final dynamic setTemperature;
  final String? communicationStatus;

  final DateTime receivedAt;

  ChillerTelemetry({
    this.waterPump,
    this.compressor1,
    this.compressor2,
    this.electricHeater,
    this.condensateFan,
    this.makeupPump,
    this.outletWaterTemp,
    this.returnWaterTemp,
    this.outletWaterPressure,
    this.returnWaterPressure,
    this.ambientTemp,
    this.faultCode,
    this.controlMode,
    this.setTemperature,
    this.communicationStatus,
    required this.receivedAt,
  });

  factory ChillerTelemetry.fromJson(Map<String, dynamic> json) {
    return ChillerTelemetry(
      waterPump: json['water_pump']?.toString(),
      compressor1: json['compressor1']?.toString(),
      compressor2: json['compressor2']?.toString(),
      electricHeater: json['electric_heater']?.toString(),
      condensateFan: json['condensate_fan']?.toString(),
      makeupPump: json['makeup_pump']?.toString(),
      outletWaterTemp: _toDouble(json['outlet_water_temp']),
      returnWaterTemp: _toDouble(json['return_water_temp']),
      outletWaterPressure: _toDouble(json['outlet_water_pressure']),
      returnWaterPressure: _toDouble(json['return_water_pressure']),
      ambientTemp: _toDouble(json['ambient_temp']),
      faultCode: json['fault_code'],
      controlMode: json['control_mode'],
      setTemperature: json['set_temperature'],
      communicationStatus: json['communication_status']?.toString(),
      receivedAt: DateTime.now(),
    );
  }

  static double? _toDouble(dynamic value) {
    if (value == null) return null;
    if (value is num) return value.toDouble();
    return double.tryParse(value.toString());
  }

  bool get isOnline {
    final status = communicationStatus?.toLowerCase();
    return status == 'online' || status == 'mock';
  }
}