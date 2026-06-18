import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_dashboard/features/assets/widgets/widgets.dart';
import 'package:flutter_dashboard/models/models.dart';

void main() {
  testWidgets('dynamic asset summary panel renders asset catalog', (tester) async {
    final assets = AssetListResponse.fromJson({
      'status': 'ok',
      'gateway_id': 'imx93_gateway_1',
      'timestamp': '2026-06-12T10:00:00+05:30',
      'assets_count': 2,
      'summary': {'total': 2, 'running': 1},
      'assets': [
        {
          'asset_id': 'pcs_1',
          'asset_key': 'pcs',
          'asset_type': 'pcs',
          'enabled': true,
          'running': true,
          'online': true,
          'protocol': 'modbus_tcp',
          'profile': 'njoy_125kw',
          'vendor': 'njoy',
          'configured': true,
          'telemetry_available': true,
          'runtime_mode': 'active_service',
          'compatibility': {},
          'connection': {'host': '192.168.1.200', 'port': 502},
          'metadata': {},
        },
        {
          'asset_id': 'bms_1',
          'asset_key': 'bms',
          'asset_type': 'bms',
          'enabled': true,
          'running': false,
          'online': false,
          'protocol': 'modbus_tcp',
          'profile': 'simulator_modbus_tcp',
          'vendor': 'simulator',
          'configured': true,
          'telemetry_available': false,
          'runtime_mode': 'configured_only',
          'compatibility': {},
          'connection': {'host': '192.168.10.1', 'port': 502},
          'metadata': {},
        },
      ],
    });

    final health = AssetsHealthResponse.fromJson({
      'status': 'ok',
      'timestamp': '2026-06-12T10:00:00+05:30',
      'summary': {'healthy': 1, 'degraded': 1},
      'assets': {
        'pcs_1': {
          'status': 'healthy',
          'asset_id': 'pcs_1',
          'asset_key': 'pcs',
          'asset_type': 'pcs',
          'enabled': true,
          'running': true,
          'online': true,
          'runtime_mode': 'active_service',
          'connection': {},
          'consecutive_failures': 0,
          'storage': {},
        },
        'bms_1': {
          'status': 'degraded',
          'asset_id': 'bms_1',
          'asset_key': 'bms',
          'asset_type': 'bms',
          'enabled': true,
          'running': false,
          'online': false,
          'runtime_mode': 'configured_only',
          'connection': {},
          'consecutive_failures': 1,
          'recommended_action': 'Check BMS simulator',
          'storage': {},
        },
      },
    });

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: DynamicAssetSummaryPanel(
              assets: assets,
              health: health,
              loading: false,
              error: null,
              onRefresh: () {},
            ),
          ),
        ),
      ),
    );

    expect(find.text('Dynamic Asset Runtime'), findsOneWidget);
    expect(find.text('pcs_1'), findsOneWidget);
    expect(find.text('bms_1'), findsOneWidget);
    expect(find.textContaining('Check BMS simulator'), findsOneWidget);
  });
}
