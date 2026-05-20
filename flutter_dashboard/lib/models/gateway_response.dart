class GatewayResponse {
  final String? type;
  final String? requestId;
  final String? timestamp;
  final String? status;
  final String? command;
  final String? message;
  final Map<String, dynamic> data;

  GatewayResponse({
    this.type,
    this.requestId,
    this.timestamp,
    this.status,
    this.command,
    this.message,
    required this.data,
  });

  factory GatewayResponse.fromJson(Map<String, dynamic> json) {
    return GatewayResponse(
      type: json['type']?.toString(),
      requestId: json['request_id']?.toString(),
      timestamp: json['timestamp']?.toString(),
      status: json['status']?.toString(),
      command: json['command']?.toString(),
      message: json['message']?.toString(),
      data: json['data'] is Map<String, dynamic>
          ? Map<String, dynamic>.from(json['data'])
          : {},
    );
  }

  bool get isOk => status?.toLowerCase() == 'ok';
}