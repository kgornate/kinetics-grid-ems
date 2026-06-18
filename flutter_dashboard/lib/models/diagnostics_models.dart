import '../core/utils/json_utils.dart';
import 'health_models.dart';

class DiagnosticItem {
  final String severity;
  final String status;
  final String? reason;
  final String? lastError;
  final String? recommendedAction;
  final Map<String, dynamic> connection;
  final String? storageStatus;
  final Map<String, dynamic> raw;

  const DiagnosticItem({
    required this.severity,
    required this.status,
    required this.reason,
    required this.lastError,
    required this.recommendedAction,
    required this.connection,
    required this.storageStatus,
    required this.raw,
  });

  factory DiagnosticItem.fromJson(Map<String, dynamic> json) {
    return DiagnosticItem(
      severity: JsonUtils.asString(json['severity']) ?? 'unknown',
      status: JsonUtils.asString(json['status']) ?? 'unknown',
      reason: JsonUtils.asString(json['reason']),
      lastError: JsonUtils.asString(json['last_error']),
      recommendedAction: JsonUtils.asString(json['recommended_action']),
      connection: JsonUtils.asMap(json['connection']),
      storageStatus: JsonUtils.asString(json['storage_status']),
      raw: Map<String, dynamic>.from(json),
    );
  }
}

class AssetDiagnosticsResponse {
  final String status;
  final String? timestamp;
  final String assetId;
  final DiagnosticItem? diagnostics;
  final AssetHealthModel? health;
  final Map<String, dynamic> raw;

  const AssetDiagnosticsResponse({
    required this.status,
    required this.timestamp,
    required this.assetId,
    required this.diagnostics,
    required this.health,
    required this.raw,
  });

  factory AssetDiagnosticsResponse.fromJson(Map<String, dynamic> json) {
    final diag = JsonUtils.asMap(json['diagnostics']);
    final health = JsonUtils.asMap(json['health']);
    return AssetDiagnosticsResponse(
      status: JsonUtils.asString(json['status']) ?? 'unknown',
      timestamp: JsonUtils.asString(json['timestamp']),
      assetId: JsonUtils.asString(json['asset_id']) ?? '',
      diagnostics: diag.isEmpty ? null : DiagnosticItem.fromJson(diag),
      health: health.isEmpty ? null : AssetHealthModel.fromJson(health),
      raw: Map<String, dynamic>.from(json),
    );
  }
}

class DiagnosticsResponse {
  final String status;
  final String? timestamp;
  final Map<String, dynamic> gateway;
  final Map<String, DiagnosticItem> diagnostics;
  final Map<String, dynamic> raw;

  const DiagnosticsResponse({
    required this.status,
    required this.timestamp,
    required this.gateway,
    required this.diagnostics,
    required this.raw,
  });

  factory DiagnosticsResponse.fromJson(Map<String, dynamic> json) {
    final rawDiagnostics = JsonUtils.asMap(json['diagnostics']);
    final parsed = <String, DiagnosticItem>{};
    for (final entry in rawDiagnostics.entries) {
      final value = JsonUtils.asMap(entry.value);
      if (value.isNotEmpty) {
        parsed[entry.key] = DiagnosticItem.fromJson(value);
      }
    }
    return DiagnosticsResponse(
      status: JsonUtils.asString(json['status']) ?? 'unknown',
      timestamp: JsonUtils.asString(json['timestamp']),
      gateway: JsonUtils.asMap(json['gateway']),
      diagnostics: parsed,
      raw: Map<String, dynamic>.from(json),
    );
  }
}
