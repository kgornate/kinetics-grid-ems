import '../../../models/log_filter_model.dart';

/// Builds backend-aligned LogFilterModel instances for telemetry, event, and
/// error log queries. This keeps URL/query details out of LogsScreen.
class LogFilterBuilder {
  static String? text(String text) {
    final trimmed = text.trim();
    return trimmed.isEmpty ? null : trimmed;
  }

  static String? dropdown(String value) {
    return value.toLowerCase() == 'all' ? null : value;
  }

  static LogFilterModel telemetry({
    required String assetId,
    required String date,
    required int limit,
    String? startTime,
    String? endTime,
    String? fields,
    String? modbusStatus,
    String? loggerStatus,
    String? vendor,
    String? commStatus,
    String? operatingStatus,
    String? faultStatus,
    String? search,
  }) {
    return LogFilterModel(
      assetId: assetId,
      date: date,
      startTime: startTime,
      endTime: endTime,
      fields: fields == null || fields.isEmpty ? null : fields.split(','),
      limit: limit,
      search: search,
      exactFilters: {
        'modbus_status': modbusStatus,
        'logger_status': loggerStatus,
        'vendor': vendor,
        'comm_status': commStatus,
        'operating_status': operatingStatus,
        'fault_status': faultStatus,
      },
    );
  }

  static LogFilterModel events({
    required String assetId,
    required int limit,
    String? date,
    String? startTime,
    String? endTime,
    String? eventType,
    String? status,
    String? command,
    String? vendor,
    String? search,
    String? fields,
  }) {
    return LogFilterModel(
      assetId: assetId,
      date: date,
      startTime: startTime,
      endTime: endTime,
      fields: fields == null || fields.isEmpty ? null : fields.split(','),
      limit: limit,
      search: search,
      exactFilters: {
        'event_type': eventType,
        'status': status,
        'command': command,
        'vendor': vendor,
      },
    );
  }

  static LogFilterModel errors({
    required String assetId,
    required int limit,
    String? date,
    String? startTime,
    String? endTime,
    String? errorType,
    String? errorSource,
    String? search,
    String? fields,
  }) {
    return LogFilterModel(
      assetId: assetId,
      date: date,
      startTime: startTime,
      endTime: endTime,
      fields: fields == null || fields.isEmpty ? null : fields.split(','),
      limit: limit,
      search: search,
      exactFilters: {
        'error_type': errorType,
        'error_source': errorSource,
      },
    );
  }
}
