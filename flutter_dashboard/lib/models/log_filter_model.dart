/// Typed log filter request used by repositories and future log screens.
class LogFilterModel {
  final String assetId;
  final String? date;
  final String? startTime;
  final String? endTime;
  final List<String>? fields;
  final int limit;
  final int? offset;
  final String? order;
  final String? search;
  final Map<String, String?> exactFilters;

  const LogFilterModel({
    required this.assetId,
    this.date,
    this.startTime,
    this.endTime,
    this.fields,
    this.limit = 100,
    this.offset,
    this.order,
    this.search,
    this.exactFilters = const <String, String?>{},
  });

  Map<String, String?> toQueryParameters() {
    return <String, String?>{
      'asset_id': assetId,
      'date': date,
      'start_time': startTime,
      'end_time': endTime,
      'fields': fields?.join(','),
      'limit': limit.toString(),
      'offset': offset?.toString(),
      'order': order,
      'search': search,
      ...exactFilters,
    };
  }

  LogFilterModel copyWith({
    String? assetId,
    String? date,
    String? startTime,
    String? endTime,
    List<String>? fields,
    int? limit,
    int? offset,
    String? order,
    String? search,
    Map<String, String?>? exactFilters,
  }) {
    return LogFilterModel(
      assetId: assetId ?? this.assetId,
      date: date ?? this.date,
      startTime: startTime ?? this.startTime,
      endTime: endTime ?? this.endTime,
      fields: fields ?? this.fields,
      limit: limit ?? this.limit,
      offset: offset ?? this.offset,
      order: order ?? this.order,
      search: search ?? this.search,
      exactFilters: exactFilters ?? this.exactFilters,
    );
  }
}
