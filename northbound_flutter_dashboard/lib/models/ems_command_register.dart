class EmsCommandRegister {
  const EmsCommandRegister({
    required this.signalName,
    required this.displayName,
    required this.address,
    required this.registerQty,
    required this.unit,
    required this.description,
    required this.writable,
    this.sourceId,
    this.assetId,
    this.category,
  });

  final String signalName;
  final String displayName;
  final int address;
  final int registerQty;
  final String unit;
  final String description;
  final bool writable;
  final String? sourceId;
  final String? assetId;
  final String? category;

  factory EmsCommandRegister.fromJson(Map<String, dynamic> json) {
    final rw = json['rw'] ?? json['writable'] ?? json['is_writable'];
    return EmsCommandRegister(
      signalName: json['signal_name']?.toString() ?? json['name']?.toString() ?? json['point_name']?.toString() ?? '',
      displayName: json['display_name']?.toString() ?? json['point_name']?.toString() ?? json['signal_name']?.toString() ?? 'Command register',
      address: _asInt(json['address'] ?? json['register_address']),
      registerQty: _asInt(json['register_qty'] ?? json['register_count'] ?? json['qty']),
      unit: json['unit']?.toString() ?? '',
      description: json['description']?.toString() ?? '',
      writable: rw == true || rw == 1 || rw?.toString() == '1',
      sourceId: json['source_id']?.toString(),
      assetId: json['asset_id']?.toString() ?? json['base_asset_id']?.toString(),
      category: json['category']?.toString(),
    );
  }

  static int _asInt(dynamic value) {
    if (value == null) return 0;
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value.toString()) ?? 0;
  }
}
