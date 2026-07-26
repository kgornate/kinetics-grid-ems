import 'package:flutter_test/flutter_test.dart';
import 'package:kinetics_gateway_dashboard/models/gateway_models.dart';

void main() {
  test('compact snapshot and delta update are merged', () {
    final plant = PlantSnapshot();
    plant.applyMessage({
      'type': 'snapshot',
      'sequence': 1,
      'gateway_id': 'gw',
      'mode': 'mock',
      'bank': {
        'asset_id': 'bms_bank',
        'asset_type': 'bms_bank',
        'online': true,
        'telemetry': {
          'soc': {'v': 50.0, 'q': 'good', 'u': '%'},
        },
      },
      'racks': [],
      'environment': {},
      'pcs': {
        'asset_id': 'pcs_1',
        'asset_type': 'pcs',
        'online': false,
        'telemetry': {},
      },
      'alarms': [],
    });

    plant.applyMessage({
      'type': 'telemetry_update',
      'sequence': 2,
      'assets': [
        {
          'asset_id': 'bms_bank',
          'asset_type': 'bms_bank',
          'online': true,
          'telemetry': {
            'soc': {'v': 51.2, 'q': 'good', 'u': '%'},
          },
        },
      ],
    });

    expect(plant.sequence, 2);
    expect(plant.bank?.point('soc')?.value, 51.2);
    expect(plant.bank?.point('soc')?.displayWithUnit, '51.2 %');
  });
}
