class ValueFormatters {
  const ValueFormatters._();

  static String bytesFromMb(num? mb) {
    if (mb == null) return '-';
    if (mb >= 1024) return '${(mb / 1024).toStringAsFixed(2)} GB';
    return '${mb.toStringAsFixed(0)} MB';
  }

  static String compactDateTime(String? value) {
    if (value == null || value.isEmpty) return '-';
    final normalized = value.replaceFirst('T', ' ');
    if (normalized.length <= 19) return normalized;
    return normalized.substring(0, 19);
  }

  static String valueWithUnit(dynamic value, String? unit) {
    final v = value == null ? '-' : value.toString();
    if (unit == null || unit.isEmpty) return v;
    return '$v $unit';
  }
}
