import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_dashboard/config/app_config.dart';
import 'package:flutter_dashboard/features/logs/controllers/log_filter_builder.dart';
import 'package:flutter_dashboard/features/logs/log_field_catalog.dart';

void main() {
  test('log field catalog returns backend-aligned defaults', () {
    final pcsFields = LogFieldCatalog.defaultTelemetryFields(AppConfig.pcsAssetId);
    final bmsFields = LogFieldCatalog.defaultTelemetryFields(AppConfig.bmsAssetId);
    final chillerFields = LogFieldCatalog.defaultTelemetryFields(AppConfig.chillerAssetId);

    expect(pcsFields, contains('active_power_kw'));
    expect(pcsFields, contains('comm_status'));
    expect(bmsFields, contains('soc_percent'));
    expect(bmsFields, contains('rack_voltage_v'));
    expect(chillerFields, contains('outlet_water_temp'));
    expect(chillerFields, contains('modbus_status'));
  });

  test('telemetry filter builder maps UI values into backend query model', () {
    final filter = LogFilterBuilder.telemetry(
      assetId: AppConfig.pcsAssetId,
      date: '2026-06-12',
      limit: 50,
      startTime: '10:00',
      endTime: '12:00',
      fields: 'timestamp,active_power_kw,comm_status',
      vendor: 'njoy',
      commStatus: 'online',
      search: 'target',
    );

    final query = filter.toQueryParameters();

    expect(query['asset_id'], AppConfig.pcsAssetId);
    expect(query['date'], '2026-06-12');
    expect(query['fields'], 'timestamp,active_power_kw,comm_status');
    expect(query['vendor'], 'njoy');
    expect(query['comm_status'], 'online');
    expect(query['search'], 'target');
  });

  test('event and error filter builders preserve exact filters', () {
    final eventFilter = LogFilterBuilder.events(
      assetId: AppConfig.pcsAssetId,
      limit: 20,
      eventType: 'PCS_ACTIVE_POWER_WRITE',
      status: 'success',
      command: 'PCS_SET_ACTIVE_POWER',
    );
    final errorFilter = LogFilterBuilder.errors(
      assetId: AppConfig.bmsAssetId,
      limit: 20,
      errorType: 'communication',
      errorSource: 'modbus',
    );

    expect(eventFilter.toQueryParameters()['event_type'], 'PCS_ACTIVE_POWER_WRITE');
    expect(eventFilter.toQueryParameters()['status'], 'success');
    expect(eventFilter.toQueryParameters()['command'], 'PCS_SET_ACTIVE_POWER');
    expect(errorFilter.toQueryParameters()['error_type'], 'communication');
    expect(errorFilter.toQueryParameters()['error_source'], 'modbus');
  });
}
