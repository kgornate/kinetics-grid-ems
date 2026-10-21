import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kalpa_gateway_dashboard/core/state/gateway_controller.dart';
import 'package:kalpa_gateway_dashboard/screens/kalpa_monitoring_screen.dart';
import 'package:kalpa_gateway_dashboard/screens/meter_screen.dart';

void main() {
  test(
    'normalized number formatter preserves zero and rejects absent/nonfinite values',
    () {
      expect(kalpaNumber(0, 'kW'), '0.0 kW');
      expect(kalpaNumber(null), '—');
      expect(kalpaNumber(double.nan), '—');
      expect(kalpaNumber(-12.5, 'kW'), '-12.5 kW');
    },
  );
  testWidgets('meter shows offline dashes and masks retained measurements', (
    tester,
  ) async {
    final controller = GatewayController();
    controller.meterReceivedAt = DateTime.now();
    controller.meter = {
      'online': false,
      'status': 'offline',
      'source': 'hardware',
      'telemetry': {
        'active_power_total_kw': {'value': 123.45, 'quality': 'good'},
      },
    };
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MeterScreen(controller: controller, active: false),
        ),
      ),
    );
    expect(find.text('offline'), findsOneWidget);
    expect(find.text('123.45 kW'), findsNothing);
    expect(find.text('—'), findsWidgets);
    await tester.pumpWidget(const SizedBox());
    controller.dispose();
  });
  testWidgets(
    'meter displays signed physical power and simulation source separately',
    (tester) async {
      final controller = GatewayController();
      controller.meterReceivedAt = DateTime.now();
      controller.meter = {
        'online': true,
        'status': 'online',
        'source': 'hardware',
        'telemetry': {
          'active_power_total_kw': {'value': -12.5, 'quality': 'good'},
        },
      };
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: MeterScreen(controller: controller, active: false),
          ),
        ),
      );
      expect(find.text('-12.50 kW'), findsOneWidget);
      expect(find.textContaining('SIMULATED METER DATA'), findsNothing);
      await tester.pumpWidget(const SizedBox());
      controller.dispose();
    },
  );
}
