/// Utility helpers for HTTP query parameters.
class QueryUtils {
  QueryUtils._();

  static Map<String, String> clean(Map<String, String?> query) {
    final cleaned = <String, String>{};
    query.forEach((key, value) {
      if (value == null) return;
      final trimmed = value.trim();
      if (trimmed.isEmpty) return;
      if (trimmed.toLowerCase() == 'all') return;
      cleaned[key] = trimmed;
    });
    return cleaned;
  }
}
