import '../../../core/config/app_connection_config.dart';

class AuthSession {
  final String accessToken;
  final String tokenType;
  final int expiresInSec;
  final String username;
  final String role;
  final String displayName;
  final AppConnectionConfig connection;

  const AuthSession({
    required this.accessToken,
    required this.tokenType,
    required this.expiresInSec,
    required this.username,
    required this.role,
    required this.displayName,
    required this.connection,
  });

  bool get isInternal => role == 'internal_admin';
  bool get isCustomer => role == 'customer_admin';

  factory AuthSession.fromLoginJson({
    required Map<String, dynamic> loginJson,
    required AppConnectionConfig connection,
  }) {
    return AuthSession(
      accessToken: loginJson['access_token'] as String? ?? '',
      tokenType: loginJson['token_type'] as String? ?? 'bearer',
      expiresInSec: (loginJson['expires_in_sec'] as num?)?.toInt() ?? 0,
      username: loginJson['username'] as String? ?? '',
      role: loginJson['role'] as String? ?? '',
      displayName: loginJson['display_name'] as String? ?? '',
      connection: connection,
    );
  }

  Map<String, dynamic> toJson() => {
        'access_token': accessToken,
        'token_type': tokenType,
        'expires_in_sec': expiresInSec,
        'username': username,
        'role': role,
        'display_name': displayName,
        'connection': connection.toJson(),
      };

  factory AuthSession.fromJson(Map<String, dynamic> json) {
    return AuthSession(
      accessToken: json['access_token'] as String? ?? '',
      tokenType: json['token_type'] as String? ?? 'bearer',
      expiresInSec: (json['expires_in_sec'] as num?)?.toInt() ?? 0,
      username: json['username'] as String? ?? '',
      role: json['role'] as String? ?? '',
      displayName: json['display_name'] as String? ?? '',
      connection: AppConnectionConfig.fromJson(
        (json['connection'] as Map?)?.cast<String, dynamic>() ?? const {},
      ),
    );
  }
}
