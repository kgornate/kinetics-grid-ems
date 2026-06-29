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

  factory TelemetrySignal.fromEntry(String key, dynamic raw) {
    final json = raw is Map ? Map<String, dynamic>.from(raw) : <String, dynamic>{};
    return TelemetrySignal(
      name: key,
      displayName: json['display_name']?.toString() ?? key,
      value: json['value'],
      unit: json['unit']?.toString(),
      quality: json['quality']?.toString() ?? 'unknown',
      category: json['category']?.toString() ?? 'general',
      timestampUtc: json['timestamp_utc']?.toString(),
      enumText: json['enum_text']?.toString(),
      address: json['address'] is int ? json['address'] as int : int.tryParse(json['address']?.toString() ?? ''),
    );
  }

  String get valueText {
    if (enumText != null && enumText!.isNotEmpty) {
      return '$value ($enumText)';
    }
    if (unit != null && unit!.isNotEmpty) {
      return '$value $unit';
    }
    return value?.toString() ?? '-';
  }
}
