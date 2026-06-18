import '../services/gateway_api_service.dart';
import '../services/log_api_service.dart';
import '../services/tcp_command_service.dart';
import '../config/app_config.dart';
import 'asset_repository.dart';
import 'command_repository.dart';
import 'diagnostics_repository.dart';
import 'gateway_repository.dart';
import 'health_repository.dart';
import 'log_repository.dart';
import 'telemetry_repository.dart';

/// Convenience bundle for screens that need multiple repositories.
class GatewayRepositoryBundle {
  final GatewayRepository gateway;
  final AssetRepository assets;
  final TelemetryRepository telemetry;
  final HealthRepository health;
  final DiagnosticsRepository diagnostics;
  final LogRepository logs;
  final CommandRepository commands;

  const GatewayRepositoryBundle({
    required this.gateway,
    required this.assets,
    required this.telemetry,
    required this.health,
    required this.diagnostics,
    required this.logs,
    required this.commands,
  });

  factory GatewayRepositoryBundle.forGateway(String gatewayIp) {
    final gatewayApi = GatewayApiService(gatewayIp: gatewayIp);
    final logApi = LogApiService(gatewayIp: gatewayIp);
    final tcp = TcpCommandService(
      gatewayIp: gatewayIp,
      gatewayPort: AppConfig.tcpCommandPort,
      timeout: AppConfig.tcpTimeout,
    );

    return GatewayRepositoryBundle(
      gateway: GatewayRepository(api: gatewayApi),
      assets: AssetRepository(api: gatewayApi),
      telemetry: TelemetryRepository(api: gatewayApi),
      health: HealthRepository(api: gatewayApi),
      diagnostics: DiagnosticsRepository(api: gatewayApi),
      logs: LogRepository(api: logApi),
      commands: CommandRepository(tcp: tcp),
    );
  }
}
