import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import '../lib/core/state/gateway_controller.dart';
import '../lib/models/gateway_models.dart';
import '../lib/screens/kalpa_monitoring_screen.dart';

class TestGatewayController extends GatewayController {
  void emitCachedUpdate() => notifyListeners();
}

Map<String, dynamic> sampleAsset(String id, String type, {int? rackId}) => {
  'asset_id': id,
  'asset_type': type,
  'rack_id': rackId,
  'online': true,
  'telemetry': {
    'rack_voltage': {'value': 1301.0, 'unit': 'V', 'quality': 'mock'},
    'cell_voltage_1': {'value': 3.25, 'unit': 'V', 'quality': 'mock'},
    'cell_temperature_1': {'value': 25.0, 'quality': 'mock'},
    'pack_positive_pole_temperature_1': {'value': 26.0, 'quality': 'mock'},
  },
};

void setViewport(WidgetTester tester, double width) {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = Size(width, 900);
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

Future<void> selectTab(WidgetTester tester, String title) async {
  final tab = find.widgetWithText(Tab, title);
  await tester.ensureVisible(tab);
  await tester.tap(tab);
  await tester.pumpAndSettle();
  expect(tester.takeException(), isNull);
}

Future<void> closeApp(WidgetTester tester, GatewayController controller) async {
  await tester.pumpWidget(const SizedBox());
  controller.dispose();
}

void main() {
  for (final width in [1280.0, 480.0]) {
    for (var rack = 1; rack <= 4; rack++) {
      testWidgets('rack $rack has categorized details at width $width', (
        tester,
      ) async {
        setViewport(tester, width);
        final id = 'bms_rack_$rack';
        final controller = GatewayController();
        controller.plant.assets[id] = AssetSnapshot.fromJson(
          sampleAsset(id, 'bms_rack', rackId: rack),
        );
        controller.normalizedReceivedAt = DateTime.now();
        controller.normalized = {
          'battery_racks': {
            '$rack': {'asset_id': id, 'online': true, 'voltage_v': 1301.0},
          },
        };
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: KalpaMonitoringScreen(
                controller: controller,
                section: 'racks',
              ),
            ),
          ),
        );
        await tester.tap(find.text('Open rack dashboard'));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        expect(find.byType(TabBar), findsOneWidget);
        expect(find.text('Rack $rack overview'), findsOneWidget);
        await selectTab(tester, 'Cells');
        expect(find.text('Individual cell voltages'), findsOneWidget);
        expect(find.text('cell_voltage_1'), findsOneWidget);
        await selectTab(tester, 'Sensors');
        expect(find.text('Pack terminal temperatures'), findsOneWidget);
        await tester.pageBack();
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        expect(find.text('Battery racks'), findsOneWidget);
        await closeApp(tester, controller);
      });
    }
  }
  testWidgets('cell table updates and remains searchable', (tester) async {
    setViewport(tester, 1280);
    final controller = TestGatewayController();
    const id = 'bms_rack_1';
    controller.plant.assets[id] = AssetSnapshot.fromJson(
      sampleAsset(id, 'bms_rack', rackId: 1),
    );
    await tester.pumpWidget(
      MaterialApp(
        home: KalpaAssetScreen(controller: controller, assetId: id),
      ),
    );
    await selectTab(tester, 'Cells');
    await tester.enterText(
      find.byKey(const ValueKey('search:Individual cell voltages')),
      'cell_voltage',
    );
    controller.plant.assets[id]!.merge({
      'telemetry': {
        'cell_voltage_2': {'value': 3.26, 'unit': 'V', 'quality': 'mock'},
      },
    });
    controller.emitCachedUpdate();
    await tester.pumpAndSettle();
    expect(find.text('cell_voltage_2'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await closeApp(tester, controller);
  });
  testWidgets('missing cached asset has an explicit empty state', (
    tester,
  ) async {
    final controller = GatewayController();
    await tester.pumpWidget(
      MaterialApp(
        home: KalpaAssetScreen(controller: controller, assetId: 'missing'),
      ),
    );
    expect(find.textContaining('No cached telemetry'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await closeApp(tester, controller);
  });
  testWidgets('PCS has separate DC, grid and settings tabs', (tester) async {
    setViewport(tester, 1280);
    final controller = GatewayController();
    controller.plant.assets['pcs_1'] = AssetSnapshot.fromJson({
      'asset_id': 'pcs_1',
      'asset_type': 'pcs',
      'online': true,
      'telemetry': {
        'dc_voltage': {'value': 1300.0, 'quality': 'good'},
        'grid_voltage_ab': {'value': 400.0, 'quality': 'good'},
        'active_power_setpoint_percent': {'value': 0.0, 'quality': 'good'},
      },
    });
    await tester.pumpWidget(
      MaterialApp(
        home: KalpaAssetScreen(controller: controller, assetId: 'pcs_1'),
      ),
    );
    await selectTab(tester, 'DC side');
    expect(find.text('DC-side measurements'), findsOneWidget);
    await selectTab(tester, 'AC / Grid');
    expect(find.text('AC / grid measurements'), findsOneWidget);
    await selectTab(tester, 'Settings');
    expect(find.text('Configuration and thresholds'), findsOneWidget);
    await closeApp(tester, controller);
  });
  testWidgets('cooling measurements are separate from settings', (
    tester,
  ) async {
    setViewport(tester, 1280);
    final controller = GatewayController();
    controller.plant.assets['liquid_cooling'] = AssetSnapshot.fromJson({
      'asset_id': 'liquid_cooling',
      'asset_type': 'liquid_cooling',
      'online': true,
      'telemetry': {
        'outlet_water_temperature': {'value': 25.0, 'quality': 'good'},
        'set_cooling_start_temperature': {'value': 27.0, 'quality': 'good'},
      },
    });
    await tester.pumpWidget(
      MaterialApp(
        home: KalpaAssetScreen(
          controller: controller,
          assetId: 'liquid_cooling',
        ),
      ),
    );
    await selectTab(tester, 'Measurements');
    expect(find.text('Cooling measurements'), findsOneWidget);
    expect(find.text('set_cooling_start_temperature'), findsNothing);
    await selectTab(tester, 'Settings');
    expect(find.text('Configuration and thresholds'), findsOneWidget);
    await closeApp(tester, controller);
  });
}
