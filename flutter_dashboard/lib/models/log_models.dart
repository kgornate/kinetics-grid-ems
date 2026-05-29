class StorageStatus {
  final String status;
  final String basePath;
  final String assetId;
  final bool exists;
  final bool telemetryDirExists;
  final bool eventsFileExists;
  final bool errorsFileExists;
  final bool metadataFileExists;
  final int telemetryFilesCount;
  final List<String> telemetryFiles;
  final String? latestTelemetryFile;

  final int diskTotalBytes;
  final int diskUsedBytes;
  final int diskFreeBytes;

  final int logTotalBytes;
  final int telemetryLogBytes;
  final int eventLogBytes;
  final int errorLogBytes;
  final int metadataBytes;

  final Map<String, dynamic> raw;

  StorageStatus({
    required this.status,
    required this.basePath,
    required this.assetId,
    required this.exists,
    required this.telemetryDirExists,
    required this.eventsFileExists,
    required this.errorsFileExists,
    required this.metadataFileExists,
    required this.telemetryFilesCount,
    required this.telemetryFiles,
    required this.latestTelemetryFile,
    required this.diskTotalBytes,
    required this.diskUsedBytes,
    required this.diskFreeBytes,
    required this.logTotalBytes,
    required this.telemetryLogBytes,
    required this.eventLogBytes,
    required this.errorLogBytes,
    required this.metadataBytes,
    required this.raw,
  });

  factory StorageStatus.fromJson(Map<String, dynamic> json) {
    return StorageStatus(
      status: json['status']?.toString() ?? 'unknown',
      basePath: json['base_path']?.toString() ?? '',
      assetId: json['asset_id']?.toString() ?? '',
      exists: json['exists'] == true,
      telemetryDirExists: json['telemetry_dir_exists'] == true,
      eventsFileExists: json['events_file_exists'] == true,
      errorsFileExists: json['errors_file_exists'] == true,
      metadataFileExists: json['metadata_file_exists'] == true,
      telemetryFilesCount: _toInt(json['telemetry_files_count']),
      telemetryFiles: _toStringList(json['telemetry_files']),
      latestTelemetryFile: json['latest_telemetry_file']?.toString(),
      diskTotalBytes: _toInt(json['disk_total_bytes']),
      diskUsedBytes: _toInt(json['disk_used_bytes']),
      diskFreeBytes: _toInt(json['disk_free_bytes']),
      logTotalBytes: _toInt(json['log_total_bytes']),
      telemetryLogBytes: _toInt(json['telemetry_log_bytes']),
      eventLogBytes: _toInt(json['event_log_bytes']),
      errorLogBytes: _toInt(json['error_log_bytes']),
      metadataBytes: _toInt(json['metadata_bytes']),
      raw: Map<String, dynamic>.from(json),
    );
  }
}

class LogApiResponse {
  final String status;
  final String logType;
  final String? message;
  final String? file;
  final String? fileName;
  final String? date;
  final int totalRows;
  final int filteredRows;
  final int rowsCount;
  final int limit;
  final List<Map<String, dynamic>> rows;
  final Map<String, dynamic> raw;

  LogApiResponse({
    required this.status,
    required this.logType,
    required this.message,
    required this.file,
    required this.fileName,
    required this.date,
    required this.totalRows,
    required this.filteredRows,
    required this.rowsCount,
    required this.limit,
    required this.rows,
    required this.raw,
  });

  factory LogApiResponse.fromJson(Map<String, dynamic> json) {
    return LogApiResponse(
      status: json['status']?.toString() ?? 'unknown',
      logType: json['log_type']?.toString() ?? '',
      message: json['message']?.toString(),
      file: json['file']?.toString(),
      fileName: json['file_name']?.toString(),
      date: json['date']?.toString(),
      totalRows: _toInt(json['total_rows']),
      filteredRows: _toInt(json['filtered_rows']),
      rowsCount: _toInt(json['rows_count']),
      limit: _toInt(json['limit']),
      rows: _toMapList(json['rows']),
      raw: Map<String, dynamic>.from(json),
    );
  }

  bool get isOk => status.toLowerCase() == 'ok';
}

class LogFilesResponse {
  final String status;
  final String? message;
  final String directory;
  final int filesCount;
  final List<String> files;
  final Map<String, dynamic> raw;

  LogFilesResponse({
    required this.status,
    required this.message,
    required this.directory,
    required this.filesCount,
    required this.files,
    required this.raw,
  });

  factory LogFilesResponse.fromJson(Map<String, dynamic> json) {
    return LogFilesResponse(
      status: json['status']?.toString() ?? 'unknown',
      message: json['message']?.toString(),
      directory: json['directory']?.toString() ?? '',
      filesCount: _toInt(json['files_count']),
      files: _toStringList(json['files']),
      raw: Map<String, dynamic>.from(json),
    );
  }

  bool get isOk => status.toLowerCase() == 'ok';
}

class MetadataResponse {
  final String status;
  final String? message;
  final String file;
  final Map<String, dynamic> metadata;
  final Map<String, dynamic> raw;

  MetadataResponse({
    required this.status,
    required this.message,
    required this.file,
    required this.metadata,
    required this.raw,
  });

  factory MetadataResponse.fromJson(Map<String, dynamic> json) {
    return MetadataResponse(
      status: json['status']?.toString() ?? 'unknown',
      message: json['message']?.toString(),
      file: json['file']?.toString() ?? '',
      metadata: _toMap(json['metadata']),
      raw: Map<String, dynamic>.from(json),
    );
  }
}

int _toInt(dynamic value) {
  if (value is int) return value;
  if (value is double) return value.toInt();
  if (value is String) return int.tryParse(value) ?? 0;
  return 0;
}

List<String> _toStringList(dynamic value) {
  if (value is List) {
    return value.map((item) => item.toString()).toList();
  }

  return <String>[];
}

Map<String, dynamic> _toMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}

List<Map<String, dynamic>> _toMapList(dynamic value) {
  if (value is! List) return <Map<String, dynamic>>[];

  return value.map((item) {
    if (item is Map<String, dynamic>) return item;
    if (item is Map) return Map<String, dynamic>.from(item);

    return <String, dynamic>{
      'value': item.toString(),
    };
  }).toList();
}

String formatBytes(int bytes) {
  if (bytes <= 0) return '0 B';

  const int kb = 1024;
  const int mb = kb * 1024;
  const int gb = mb * 1024;

  if (bytes >= gb) {
    return '${(bytes / gb).toStringAsFixed(2)} GB';
  }

  if (bytes >= mb) {
    return '${(bytes / mb).toStringAsFixed(2)} MB';
  }

  if (bytes >= kb) {
    return '${(bytes / kb).toStringAsFixed(2)} KB';
  }

  return '$bytes B';
}