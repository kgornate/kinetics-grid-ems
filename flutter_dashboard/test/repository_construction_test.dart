import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_dashboard/repositories/repositories.dart';

void main() {
  test('repository bundle can be constructed', () {
    final bundle = GatewayRepositoryBundle.forGateway('192.168.10.2');

    expect(bundle.gateway, isA<GatewayRepository>());
    expect(bundle.assets, isA<AssetRepository>());
    expect(bundle.telemetry, isA<TelemetryRepository>());
    expect(bundle.health, isA<HealthRepository>());
    expect(bundle.diagnostics, isA<DiagnosticsRepository>());
    expect(bundle.logs, isA<LogRepository>());
    expect(bundle.commands, isA<CommandRepository>());
  });
}
