class SignalPreview {
  const SignalPreview({
    required this.name,
    required this.displayName,
    required this.value,
    this.unit,
    this.quality,
    this.category,
    this.enumText,
  });

  final String name;
  final String displayName;
  final dynamic value;
  final String? unit;
  final String? quality;
  final String? category;
  final String? enumText;

  factory SignalPreview.fromEntry(String key, dynamic raw) {
    if (raw is Map) {
      final json = Map<String, dynamic>.from(raw);
      return SignalPreview(
        name: key,
        displayName: json['display_name']?.toString() ?? json['point_name']?.toString() ?? _titleFromKey(key),
        value: json['value'],
        unit: json['unit']?.toString(),
        quality: json['quality']?.toString(),
        category: json['category']?.toString(),
        enumText: json['enum_text']?.toString(),
      );
    }
    return SignalPreview(name: key, displayName: _titleFromKey(key), value: raw);
  }

  String get valueText {
    final rawValue = value;
    final valuePart = rawValue == null ? '-' : _formatValue(rawValue);
    final enumPart = enumText == null || enumText!.isEmpty ? '' : ' ($enumText)';
    final unitPart = unit == null || unit!.isEmpty ? '' : ' $unit';
    return '$valuePart$unitPart$enumPart';
  }

  static String _titleFromKey(String key) {
    return key
        .split(RegExp(r'[._]'))
        .where((part) => part.isNotEmpty)
        .map((part) => part.isEmpty ? part : '${part[0].toUpperCase()}${part.substring(1)}')
        .join(' ');
  }

  static String _formatValue(dynamic value) {
    if (value is double) return value.toStringAsFixed(value.abs() >= 100 ? 1 : 2);
    if (value is num) return value.toString();
    return value.toString();
  }
}
