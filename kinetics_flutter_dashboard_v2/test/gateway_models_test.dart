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

  test('four Modbus RTU PCS devices are parsed and sorted by unit ID', () {
    final plant = PlantSnapshot();
    plant.applyMessage({
      'type': 'snapshot',
      'sequence': 10,
      'gateway_id': 'gw',
      'mode': 'read_only',
      'bank': null,
      'racks': [],
      'environment': {},
      'pcs_devices': {
        'pcs_4': {
          'asset_id': 'pcs_4',
          'asset_type': 'pcs',
          'label': 'PCS 4',
          'unit_id': 4,
          'online': false,
          'telemetry': {},
        },
        'pcs_1': {
          'asset_id': 'pcs_1',
          'asset_type': 'pcs',
          'label': 'PCS 1',
          'unit_id': 1,
          'online': true,
          'telemetry': {
            'grid_frequency': {'v': 50.01, 'q': 'good', 'u': 'Hz'},
          },
        },
        'pcs_2': {
          'asset_id': 'pcs_2',
          'asset_type': 'pcs',
          'label': 'PCS 2',
          'unit_id': 2,
          'online': false,
          'telemetry': {},
        },
        'pcs_3': {
          'asset_id': 'pcs_3',
          'asset_type': 'pcs',
          'label': 'PCS 3',
          'unit_id': 3,
          'online': false,
          'telemetry': {},
        },
      },
      'alarms': [],
    });

    expect(plant.pcsDevices.length, 4);
    expect(plant.pcsDevices.map((e) => e.unitId).toList(), [1, 2, 3, 4]);
    expect(plant.pcsDevices.first.label, 'PCS 1');
    expect(plant.pcsDevices.first.point('grid_frequency')?.value, 50.01);
  });
}

test('Stage 3C cached control sample populates the control model', () {
  final status = ControlSequenceStatus.fromJson({
    'pair': {'pair_id': 'pair_1'},
    'timestamp': '2026-07-28T19:10:00+00:00',
    'runtime': {
      'run_status': 'idle',
      'stage': 'stopped_and_bms_open_verified',
    },
    'write_gates': {
      'control_sequence_enabled': true,
      'gateway_mode': 'control_enabled',
      'bms_write_enabled': true,
      'pcs_write_enabled': true,
    },
    'summary': {
      'rack_voltage_v': 1380.8,
      'pcs_power_setpoint_kw': 0.0,
      'pcs_actual_power_kw': 0.0,
      'blockers': {
        'emergency_stop_fault': false,
        'documented_critical_fault': false,
      },
    },
    'workflow': {
      'system_state': 'stopped_safe',
      'stopped_safe': true,
      'ready_for_power': false,
      'hard_blocked': false,
      'steps': [],
    },
    'refresh': {
      'source': 'background_poll_cache',
      'stale': false,
    },
    'errors': [],
  });

  expect(status.pairId, 'pair_1');
  expect(status.systemState, 'stopped_safe');
  expect(status.controlEnabled, isTrue);
  expect(status.value('rack_voltage_v'), 1380.8);
  expect(status.errors, isEmpty);
});
