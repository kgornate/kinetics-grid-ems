class EmsCommandRegister {
  const EmsCommandRegister({
    required this.id,
    required this.assetId,
    required this.address,
    required this.registerQty,
    required this.pointName,
    required this.signalName,
    required this.pointType,
    required this.unit,
    required this.description,
    required this.factor,
    required this.category,
    this.latestValue,
    this.latestQuality,
  });

  final String id;
  final String assetId;
  final int address;
  final int registerQty;
  final String pointName;
  final String signalName;
  final String pointType;
  final String unit;
  final String description;
  final double factor;
  final String category;
  final double? latestValue;
  final String? latestQuality;

  factory EmsCommandRegister.fromJson(Map<String, dynamic> json) {
    final latest = json['latest'];
    final latestMap = latest is Map ? Map<String, dynamic>.from(latest) : const <String, dynamic>{};
    return EmsCommandRegister(
      id: json['id']?.toString() ?? '',
      assetId: json['asset_id']?.toString() ?? 'ems_system',
      address: _asInt(json['address']),
      registerQty: _asInt(json['register_qty']),
      pointName: json['point_name']?.toString() ?? '',
      signalName: json['signal_name']?.toString() ?? '',
      pointType: json['point_type']?.toString() ?? '',
      unit: json['unit']?.toString() ?? '',
      description: json['description']?.toString() ?? '',
      factor: _asDouble(json['factor'], fallback: 1),
      category: json['category']?.toString() ?? 'general',
      latestValue: latestMap.containsKey('value') ? _asNullableDouble(latestMap['value']) : null,
      latestQuality: latestMap['quality']?.toString(),
    );
  }

  String get label => '$pointName ($signalName)';

  String get valueHint {
    if (description.trim().isNotEmpty) return description.trim();
    if (unit.trim().isNotEmpty) return 'Enter value in $unit';
    return 'Enter numeric value';
  }

  static int _asInt(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '') ?? 0;
  }

  static double _asDouble(dynamic value, {double fallback = 0}) {
    if (value is num) return value.toDouble();
    return double.tryParse(value?.toString() ?? '') ?? fallback;
  }

  static double? _asNullableDouble(dynamic value) {
    if (value == null) return null;
    if (value is num) return value.toDouble();
    return double.tryParse(value.toString());
  }
}
