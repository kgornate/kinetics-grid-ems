class LogFilterOptions {
  const LogFilterOptions({
    this.severities = const [],
    this.eventTypes = const [],
    this.sources = const [],
    this.assetIds = const [],
  });

  final List<String> severities;
  final List<String> eventTypes;
  final List<String> sources;
  final List<String> assetIds;

  factory LogFilterOptions.fromJson(Map<String, dynamic> json) {
    return LogFilterOptions(
      severities: _stringList(json['severities']),
      eventTypes: _stringList(json['event_types']),
      sources: _stringList(json['sources']),
      assetIds: _stringList(json['asset_ids']),
    );
  }

  static List<String> _stringList(dynamic raw) {
    if (raw is! List) return const [];
    return raw.map((item) => item.toString()).where((item) => item.trim().isNotEmpty).toList();
  }
}
