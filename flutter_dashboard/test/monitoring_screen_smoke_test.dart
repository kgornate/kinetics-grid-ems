import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_dashboard/screens/health_dashboard_screen.dart';
import 'package:flutter_dashboard/screens/operator_dashboard_screen.dart';
import 'package:flutter_dashboard/screens/storage_health_screen.dart';
import 'package:flutter_dashboard/screens/asset_navigation_screen.dart';

void main() {
  testWidgets('new monitoring screens construct with gateway IP', (tester) async {
    const gatewayIp = '192.168.10.2';

    await tester.pumpWidget(const MaterialApp(home: HealthDashboardScreen(gatewayIp: gatewayIp)));
    expect(find.text('Health Dashboard'), findsOneWidget);

    await tester.pumpWidget(const MaterialApp(home: OperatorDashboardScreen(gatewayIp: gatewayIp)));
    expect(find.text('Operator Mode Dashboard'), findsOneWidget);

    await tester.pumpWidget(const MaterialApp(home: StorageHealthScreen(gatewayIp: gatewayIp)));
    expect(find.text('Storage Health'), findsOneWidget);

    await tester.pumpWidget(const MaterialApp(home: AssetNavigationScreen(gatewayIp: gatewayIp)));
    expect(find.text('Assets'), findsOneWidget);
  });
}
