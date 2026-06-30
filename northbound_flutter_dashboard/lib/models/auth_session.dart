class AuthSession {
  const AuthSession({
    required this.accessToken,
    required this.tokenType,
    required this.expiresInSec,
    required this.username,
    required this.role,
    required this.displayName,
  });

  final String accessToken;
  final String tokenType;
  final int expiresInSec;
  final String username;
  final String role;
  final String displayName;

  bool get isCustomerAdmin => role == 'customer_admin';
  bool get isInternalAdmin => role == 'internal_admin';

  factory AuthSession.fromJson(Map<String, dynamic> json) {
    return AuthSession(
      accessToken: json['access_token']?.toString() ?? '',
      tokenType: json['token_type']?.toString() ?? 'bearer',
      expiresInSec: _asInt(json['expires_in_sec']),
      username: json['username']?.toString() ?? '',
      role: json['role']?.toString() ?? '',
      displayName: json['display_name']?.toString() ?? json['username']?.toString() ?? '',
    );
  }

  Map<String, dynamic> toJson() => {
        'access_token': accessToken,
        'token_type': tokenType,
        'expires_in_sec': expiresInSec,
        'username': username,
        'role': role,
        'display_name': displayName,
      };

  static int _asInt(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '') ?? 0;
  }
}
