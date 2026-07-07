class ControlCommandResult {
  const ControlCommandResult({required this.ok, required this.message, required this.raw});

  final bool ok;
  final String message;
  final Map<String, dynamic> raw;

  factory ControlCommandResult.fromJson(Map<String, dynamic> json) {
    final okValue = json['ok'] ?? json['success'] ?? json['accepted'];
    return ControlCommandResult(
      ok: okValue == true || okValue?.toString().toLowerCase() == 'true',
      message: json['message']?.toString() ?? json['status']?.toString() ?? json['command']?.toString() ?? 'Command completed',
      raw: json,
    );
  }
}
