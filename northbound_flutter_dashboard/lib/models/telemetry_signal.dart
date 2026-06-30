class TelemetrySignal {
  TelemetrySignal({
    required this.name,
    required this.displayName,
    required this.value,
    required this.unit,
    required this.quality,
    required this.category,
    required this.timestampUtc,
    this.enumText,
    this.address,
    this.description,
    this.raw = const {},
  });

  final String name;
  final String displayName;
  final dynamic value;
  final String? unit;
  final String quality;
  final String category;
  final String? timestampUtc;
  final String? enumText;
  final int? address;
  final String? description;
  final Map<String, dynamic> raw;

  factory TelemetrySignal.fromEntry(String key, dynamic rawValue) {
    final json = rawValue is Map ? Map<String, dynamic>.from(rawValue) : <String, dynamic>{};
    return TelemetrySignal(
      name: key,
      displayName: json['display_name']?.toString() ?? json['point_name']?.toString() ?? key,
      value: json.containsKey('value') ? json['value'] : rawValue,
      unit: json['unit']?.toString(),
      quality: json['quality']?.toString() ?? 'unknown',
      category: json['category']?.toString() ?? 'general',
      timestampUtc: json['timestamp_utc']?.toString() ?? json['updated_utc']?.toString(),
      enumText: json['enum_text']?.toString(),
      address: json['address'] is int ? json['address'] as int : int.tryParse(json['address']?.toString() ?? ''),
      description: json['description']?.toString(),
      raw: json,
    );
  }

  String get valueText {
    final v = _formatValue(value);
    if (enumText != null && enumText!.isNotEmpty) return '$v (${enumText!})';
    if (unit != null && unit!.isNotEmpty) return '$v ${unit!}';
    return v;
  }

  bool get isGood => quality.toLowerCase() == 'good' || quality.toLowerCase() == 'ok' || quality.toLowerCase() == 'valid';

  static String _formatValue(dynamic value) {
    if (value == null) return '-';
    if (value is double) {
      final abs = value.abs();
      if (abs >= 1000) return value.toStringAsFixed(0);
      if (abs >= 100) return value.toStringAsFixed(1);
      return value.toStringAsFixed(2);
    }
    if (value is num) return value.toString();
    return value.toString();
  }
}
