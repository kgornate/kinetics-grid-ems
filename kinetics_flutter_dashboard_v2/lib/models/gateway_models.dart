import 'dart:convert';

String prettifyKey(String value) {
  final spaced = value.replaceAll(RegExp(r'[_\-]+'), ' ').trim();
  if (spaced.isEmpty) return value;
  return spaced
      .split(RegExp(r'\s+'))
      .map((part) => part.isEmpty
          ? part
          : '${part[0].toUpperCase()}${part.substring(1)}')
      .join(' ');
}

class TelemetryPoint {
  const TelemetryPoint({
    required this.value,
    required this.quality,
    this.unit,
    this.raw,
    this.bitfields = const <String, dynamic>{},
    this.bitfieldLabels = const <String, String>{},
    this.key,
    this.nameEn,
    this.nameCn,
    this.address,
    this.category,
    this.access,
    this.enumLabel,
    this.decodingStatus,
    this.hardwareValidation,
  });

  final dynamic value;
  final String quality;
  final String? unit;
  final dynamic raw;
  final Map<String, dynamic> bitfields;
  final Map<String, String> bitfieldLabels;
  final String? key;
  final String? nameEn;
  final String? nameCn;
  final String? address;
  final String? category;
  final String? access;
  final String? enumLabel;
  final String? decodingStatus;
  final String? hardwareValidation;

  factory TelemetryPoint.fromJson(dynamic json) {
    if (json is! Map) {
      return TelemetryPoint(value: json, quality: 'unknown');
    }
    final map = Map<String, dynamic>.from(json as Map);
    final bits = map['b'] ?? map['bitfields'];
    final rawLabels = map['bitfield_labels'];
    final labels = <String, String>{};
    if (rawLabels is Map) {
      for (final entry in rawLabels.entries) {
        labels[entry.key.toString()] = entry.value?.toString() ?? '';
      }
    }
    return TelemetryPoint(
      value: map.containsKey('v') ? map['v'] : map['value'],
      quality: (map['q'] ?? map['quality'] ?? 'unknown').toString(),
      unit: (map['u'] ?? map['unit'])?.toString(),
      raw: map.containsKey('r') ? map['r'] : map['raw'],
      bitfields: bits is Map ? Map<String, dynamic>.from(bits) : const {},
      bitfieldLabels: labels,
      key: map['key']?.toString(),
      nameEn: map['name_en']?.toString(),
      nameCn: map['name_cn']?.toString(),
      address: map['address']?.toString(),
      category: map['category']?.toString(),
      access: map['access']?.toString(),
      enumLabel: map['enum_label']?.toString(),
      decodingStatus: map['decoding_status']?.toString(),
      hardwareValidation: map['hardware_validation']?.toString(),
    );
  }

  String get displayValue {
    if (value == null) return '--';
    if (value is List) return '${(value as List).length} values';
    if (value is Map) return '${(value as Map).length} fields';
    if (value is double) {
      final number = value as double;
      final text = number.toStringAsFixed(3);
      return text.replaceFirst(RegExp(r'\.?0+$'), '');
    }
    return value.toString();
  }

  String get displayWithUnit {
    final suffix = unit == null || unit!.isEmpty ? '' : ' $unit';
    return '$displayValue$suffix';
  }

  bool get isGood => quality.toLowerCase() == 'good';

  Map<String, dynamic> toJson() => {
        'value': value,
        'quality': quality,
        if (unit != null) 'unit': unit,
        if (raw != null) 'raw': raw,
        if (bitfields.isNotEmpty) 'bitfields': bitfields,
        if (bitfieldLabels.isNotEmpty) 'bitfield_labels': bitfieldLabels,
        if (key != null) 'key': key,
        if (nameEn != null) 'name_en': nameEn,
        if (nameCn != null) 'name_cn': nameCn,
        if (address != null) 'address': address,
        if (category != null) 'category': category,
        if (access != null) 'access': access,
        if (enumLabel != null) 'enum_label': enumLabel,
        if (decodingStatus != null) 'decoding_status': decodingStatus,
        if (hardwareValidation != null)
          'hardware_validation': hardwareValidation,
      };
}

class AssetSnapshot {
  AssetSnapshot({
    required this.assetId,
    required this.assetType,
    required this.online,
    this.label,
    this.unitId,
    this.disabled = false,
    this.rackId,
    this.timestamp,
    this.transport,
    this.serialDevice,
    Map<String, TelemetryPoint>? telemetry,
  }) : telemetry = telemetry ?? <String, TelemetryPoint>{};

  final String assetId;
  String assetType;
  String? label;
  int? unitId;
  bool disabled;
  int? rackId;
  bool online;
  String? timestamp;
  String? transport;
  String? serialDevice;
  final Map<String, TelemetryPoint> telemetry;

  factory AssetSnapshot.fromJson(Map<String, dynamic> json) {
    final points = <String, TelemetryPoint>{};
    final rawTelemetry = json['telemetry'];
    if (rawTelemetry is Map) {
      for (final entry in rawTelemetry.entries) {
        points[entry.key.toString()] = TelemetryPoint.fromJson(entry.value);
      }
    }
    return AssetSnapshot(
      assetId: (json['asset_id'] ?? 'unknown').toString(),
      assetType: (json['asset_type'] ?? 'unknown').toString(),
      label: json['label']?.toString(),
      unitId: _asInt(json['unit_id']),
      disabled: json['disabled'] == true,
      rackId: _asInt(json['rack_id']),
      online: json['online'] == true,
      timestamp: json['timestamp']?.toString(),
      transport: json['transport']?.toString(),
      serialDevice: json['serial_device']?.toString(),
      telemetry: points,
    );
  }

  void merge(Map<String, dynamic> json) {
    if (json.containsKey('asset_type')) {
      assetType = json['asset_type']?.toString() ?? assetType;
    }
    if (json.containsKey('label')) label = json['label']?.toString();
    if (json.containsKey('unit_id')) unitId = _asInt(json['unit_id']);
    if (json.containsKey('disabled')) disabled = json['disabled'] == true;
    if (json.containsKey('rack_id')) rackId = _asInt(json['rack_id']);
    if (json.containsKey('online')) online = json['online'] == true;
    if (json['timestamp'] != null) timestamp = json['timestamp'].toString();
    if (json.containsKey('transport')) transport = json['transport']?.toString();
    if (json.containsKey('serial_device')) {
      serialDevice = json['serial_device']?.toString();
    }
    final rawTelemetry = json['telemetry'];
    if (rawTelemetry is Map) {
      for (final entry in rawTelemetry.entries) {
        final key = entry.key.toString();
        final incoming = TelemetryPoint.fromJson(entry.value);
        final existing = telemetry[key];
        telemetry[key] = existing == null
            ? incoming
            : TelemetryPoint(
                value: incoming.value,
                quality: incoming.quality,
                unit: incoming.unit ?? existing.unit,
                raw: incoming.raw,
                bitfields: incoming.bitfields.isEmpty
                    ? existing.bitfields
                    : incoming.bitfields,
                bitfieldLabels: incoming.bitfieldLabels.isEmpty
                    ? existing.bitfieldLabels
                    : incoming.bitfieldLabels,
                key: incoming.key ?? existing.key,
                nameEn: incoming.nameEn ?? existing.nameEn,
                nameCn: incoming.nameCn ?? existing.nameCn,
                address: incoming.address ?? existing.address,
                category: incoming.category ?? existing.category,
                access: incoming.access ?? existing.access,
                enumLabel: incoming.enumLabel ?? existing.enumLabel,
                decodingStatus:
                    incoming.decodingStatus ?? existing.decodingStatus,
                hardwareValidation:
                    incoming.hardwareValidation ?? existing.hardwareValidation,
              );
      }
    }
  }

  TelemetryPoint? point(String key) => telemetry[key];

  TelemetryPoint? findPoint(List<String> preferredKeys) {
    for (final key in preferredKeys) {
      final exact = telemetry[key];
      if (exact != null) return exact;
    }
    for (final key in preferredKeys) {
      final lowered = key.toLowerCase();
      for (final entry in telemetry.entries) {
        if (entry.key.toLowerCase().contains(lowered)) return entry.value;
      }
    }
    return null;
  }

  Map<String, dynamic> toJson() => {
        'asset_id': assetId,
        'asset_type': assetType,
        if (label != null) 'label': label,
        if (unitId != null) 'unit_id': unitId,
        'disabled': disabled,
        'rack_id': rackId,
        'online': online,
        'timestamp': timestamp,
        if (transport != null) 'transport': transport,
        if (serialDevice != null) 'serial_device': serialDevice,
        'telemetry': telemetry.map((key, value) => MapEntry(key, value.toJson())),
      };
}

class PlantSnapshot {
  int sequence = 0;
  String gatewayId = '';
  String mode = '';
  String? timestamp;
  final Map<String, AssetSnapshot> assets = <String, AssetSnapshot>{};
  List<Map<String, dynamic>> alarms = <Map<String, dynamic>>[];

  AssetSnapshot? get bank => assets['bms_bank'];
  AssetSnapshot? get pcs => assets['pcs_1'];

  List<AssetSnapshot> get pcsDevices {
    final result = assets.values
        .where((asset) => asset.assetType == 'pcs')
        .toList();
    result.sort((a, b) {
      final byUnit = (a.unitId ?? 999).compareTo(b.unitId ?? 999);
      if (byUnit != 0) return byUnit;
      return a.assetId.compareTo(b.assetId);
    });
    return result;
  }

  List<AssetSnapshot> get racks {
    final result = assets.values
        .where((asset) => asset.assetType == 'bms_rack')
        .toList();
    result.sort((a, b) => (a.rackId ?? 0).compareTo(b.rackId ?? 0));
    return result;
  }

  List<AssetSnapshot> get environment {
    final result = assets.values
        .where((asset) =>
            asset.assetId != 'bms_bank' &&
            asset.assetType != 'bms_rack' &&
            asset.assetType != 'pcs')
        .toList();
    result.sort((a, b) => a.assetId.compareTo(b.assetId));
    return result;
  }

  void applyMessage(Map<String, dynamic> message) {
    final type = message['type']?.toString();
    if (type == 'telemetry_update') {
      _applyUpdate(message);
      return;
    }
    if (type == 'snapshot' || message.containsKey('bank')) {
      _applySnapshot(message);
    }
  }

  void _applySnapshot(Map<String, dynamic> message) {
    sequence = _asInt(message['sequence']) ?? sequence;
    gatewayId = message['gateway_id']?.toString() ?? gatewayId;
    mode = message['mode']?.toString() ?? mode;
    timestamp = message['timestamp']?.toString() ?? timestamp;

    final bankJson = message['bank'];
    if (bankJson is Map) _upsert(Map<String, dynamic>.from(bankJson));

    final rackJson = message['racks'];
    if (rackJson is List) {
      for (final item in rackJson.whereType<Map>()) {
        _upsert(Map<String, dynamic>.from(item));
      }
    }

    final environmentJson = message['environment'];
    if (environmentJson is Map) {
      for (final item in environmentJson.values.whereType<Map>()) {
        _upsert(Map<String, dynamic>.from(item));
      }
    }

    // Legacy single-PCS field retained for older gateway versions.
    final pcsJson = message['pcs'];
    if (pcsJson is Map) _upsert(Map<String, dynamic>.from(pcsJson));

    // Current RTU gateway publishes all four Unit IDs here.
    final pcsDevicesJson = message['pcs_devices'];
    if (pcsDevicesJson is Map) {
      for (final item in pcsDevicesJson.values.whereType<Map>()) {
        _upsert(Map<String, dynamic>.from(item));
      }
    } else if (pcsDevicesJson is List) {
      for (final item in pcsDevicesJson.whereType<Map>()) {
        _upsert(Map<String, dynamic>.from(item));
      }
    }

    final alarmJson = message['alarms'];
    if (alarmJson is List) {
      alarms = alarmJson
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList();
    }
  }

  void _applyUpdate(Map<String, dynamic> message) {
    sequence = _asInt(message['sequence']) ?? sequence;
    gatewayId = message['gateway_id']?.toString() ?? gatewayId;
    timestamp = message['timestamp']?.toString() ?? timestamp;
    final updateAssets = message['assets'];
    if (updateAssets is List) {
      for (final item in updateAssets.whereType<Map>()) {
        _upsert(Map<String, dynamic>.from(item));
      }
    }
  }

  void _upsert(Map<String, dynamic> json) {
    final id = json['asset_id']?.toString();
    if (id == null || id.isEmpty) return;
    final current = assets[id];
    if (current == null) {
      assets[id] = AssetSnapshot.fromJson(json);
    } else {
      current.merge(json);
    }
  }

  String toPrettyJson() => const JsonEncoder.withIndent('  ').convert({
        'sequence': sequence,
        'gateway_id': gatewayId,
        'mode': mode,
        'timestamp': timestamp,
        'assets': assets.map((key, value) => MapEntry(key, value.toJson())),
        'alarms': alarms,
      });
}

class GatewaySession {
  const GatewaySession({
    required this.baseUrl,
    required this.token,
    required this.username,
    required this.role,
  });

  final String baseUrl;
  final String token;
  final String username;
  final String role;

  bool get isInternal => role.toLowerCase() == 'internal';
}

int? _asInt(dynamic value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '');
}

class ControlPairSummary {
  const ControlPairSummary({
    required this.pairId,
    required this.rackId,
    required this.pcsAssetId,
    required this.enabled,
  });

  factory ControlPairSummary.fromJson(Map<String, dynamic> json) {
    return ControlPairSummary(
      pairId: json['pair_id']?.toString() ?? 'pair_1',
      rackId: _asInt(json['rack_id']) ?? 1,
      pcsAssetId: json['pcs_asset_id']?.toString() ?? 'pcs_1',
      enabled: _asBool(json['enabled']) ?? false,
    );
  }

  final String pairId;
  final int rackId;
  final String pcsAssetId;
  final bool enabled;
}

class ControlSequenceCapabilities {
  const ControlSequenceCapabilities({
    required this.enabled,
    required this.fullAutomaticAllowed,
    required this.confirmationPhrase,
    required this.automaticConfirmationPhrase,
    required this.pairs,
    required this.safetyLimits,
    required this.raw,
  });

  factory ControlSequenceCapabilities.fromJson(Map<String, dynamic> json) {
    final pairItems = json['pairs'];
    return ControlSequenceCapabilities(
      enabled: _asBool(json['enabled']) ?? false,
      fullAutomaticAllowed:
          _asBool(json['full_automatic_sequence_allowed']) ?? false,
      confirmationPhrase:
          json['confirmation_phrase']?.toString() ?? 'EXECUTE_STAGE_WRITE',
      automaticConfirmationPhrase:
          json['automatic_confirmation_phrase']?.toString() ??
              'EXECUTE_AUTOMATIC_SEQUENCE',
      pairs: pairItems is List
          ? pairItems
              .whereType<Map>()
              .map((item) =>
                  ControlPairSummary.fromJson(Map<String, dynamic>.from(item)))
              .toList()
          : const <ControlPairSummary>[],
      safetyLimits: _asMap(json['safety_limits']),
      raw: Map<String, dynamic>.from(json),
    );
  }

  final bool enabled;
  final bool fullAutomaticAllowed;
  final String confirmationPhrase;
  final String automaticConfirmationPhrase;
  final List<ControlPairSummary> pairs;
  final Map<String, dynamic> safetyLimits;
  final Map<String, dynamic> raw;

  double get maxPowerKw =>
      _asDouble(safetyLimits['max_abs_power_kw']) ?? 240.0;

  double get defaultRampStepKw =>
      _asDouble(safetyLimits['automatic_power_ramp_step_kw']) ?? 10.0;

  double get defaultRampIntervalSeconds =>
      _asDouble(safetyLimits['automatic_power_ramp_interval_seconds']) ?? 1.0;
}

class ControlSequenceStep {
  const ControlSequenceStep({
    required this.key,
    required this.label,
    required this.complete,
    required this.status,
    this.message,
  });

  factory ControlSequenceStep.fromJson(Map<String, dynamic> json) {
    final status = json['status']?.toString();
    final complete = _asBool(json['complete']) ?? status == 'success';
    return ControlSequenceStep(
      key: json['key']?.toString() ?? '',
      label: json['label']?.toString() ??
          (json['key']?.toString() ?? 'Sequence step'),
      complete: complete,
      status: status ?? (complete ? 'success' : 'pending'),
      message: json['message']?.toString(),
    );
  }

  final String key;
  final String label;
  final bool complete;
  final String status;
  final String? message;

  bool get running => status == 'running';
  bool get failed => status == 'failed';
}

class ControlSequenceStatus {
  const ControlSequenceStatus({
    required this.pairId,
    required this.timestamp,
    required this.summary,
    required this.blockers,
    required this.workflow,
    required this.runtime,
    required this.writeGates,
    required this.errors,
    required this.raw,
  });

  factory ControlSequenceStatus.fromJson(Map<String, dynamic> json) {
    final pair = _asMap(json['pair']);
    final summary = _asMap(json['summary']);
    final workflow = _asMap(json['workflow']);
    final runtime = _asMap(json['runtime']);
    return ControlSequenceStatus(
      pairId: pair['pair_id']?.toString() ?? 'pair_1',
      timestamp: json['timestamp']?.toString(),
      summary: summary,
      blockers: _asMap(summary['blockers']),
      workflow: workflow,
      runtime: runtime,
      writeGates: _asMap(json['write_gates']),
      errors: json['errors'] is List
          ? List<dynamic>.from(json['errors'] as List)
          : const <dynamic>[],
      raw: Map<String, dynamic>.from(json),
    );
  }

  final String pairId;
  final String? timestamp;
  final Map<String, dynamic> summary;
  final Map<String, dynamic> blockers;
  final Map<String, dynamic> workflow;
  final Map<String, dynamic> runtime;
  final Map<String, dynamic> writeGates;
  final List<dynamic> errors;
  final Map<String, dynamic> raw;

  String get systemState => workflow['system_state']?.toString() ?? 'unknown';
  String get runStatus => runtime['run_status']?.toString() ?? 'idle';
  String? get runId => runtime['run_id']?.toString();
  String? get lastError => runtime['last_error']?.toString();
  bool get stoppedSafe => _asBool(workflow['stopped_safe']) ?? false;
  bool get readyForPower => _asBool(workflow['ready_for_power']) ?? false;
  bool get hardBlocked => _asBool(workflow['hard_blocked']) ?? false;
  bool get automaticRunning => runStatus == 'running';
  bool get controlEnabled =>
      (_asBool(writeGates['control_sequence_enabled']) ?? false) &&
      writeGates['gateway_mode']?.toString() == 'control_enabled' &&
      (_asBool(writeGates['bms_write_enabled']) ?? false) &&
      (_asBool(writeGates['pcs_write_enabled']) ?? false);

  double? value(String key) => _asDouble(summary[key]);
  bool flag(String key) => _asBool(summary[key]) ?? false;
  bool blocker(String key) => _asBool(blockers[key]) ?? false;

  List<ControlSequenceStep> get workflowSteps {
    final items = workflow['steps'];
    if (items is! List) return const <ControlSequenceStep>[];
    return items
        .whereType<Map>()
        .map((item) =>
            ControlSequenceStep.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  List<ControlSequenceStep> get runSteps {
    final items = runtime['steps'];
    if (items is! List) return const <ControlSequenceStep>[];
    return items
        .whereType<Map>()
        .map((item) =>
            ControlSequenceStep.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }
}

double? _asDouble(dynamic value) {
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString() ?? '');
}

bool? _asBool(dynamic value) {
  if (value is bool) return value;
  if (value is num) return value != 0;
  final text = value?.toString().toLowerCase();
  if (text == 'true' || text == '1') return true;
  if (text == 'false' || text == '0') return false;
  return null;
}

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}
