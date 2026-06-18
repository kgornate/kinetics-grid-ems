import '../../config/app_config.dart';

/// Central catalog for log table fields and default field selections.
///
/// Keeping this outside LogsScreen makes the log UI easier to maintain as more
/// assets and backend log fields are added.
class LogFieldCatalog {
  static const List<String> chillerTelemetryFieldOrder = [
    'timestamp',
    'sequence_no',
    'gateway_id',
    'asset_id',
    'system_on_off',
    'control_mode',
    'set_temperature',
    'outlet_water_temp',
    'return_water_temp',
    'outlet_water_pressure',
    'return_water_pressure',
    'ambient_temp',
    'water_pump_status',
    'compressor_1_status',
    'compressor_2_status',
    'electric_heater_status',
    'condensate_fan_status',
    'modbus_status',
    'logger_status',
  ];

  static const List<String> pcsTelemetryFieldOrder = [
    'timestamp',
    'sequence_no',
    'gateway_id',
    'asset_id',
    'vendor',
    'comm_status',
    'active_power_kw',
    'reactive_power_kvar',
    'apparent_power_kva',
    'power_factor',
    'frequency_hz',
    'battery_voltage_v',
    'battery_current_a',
    'dc_power_kw',
    'bus_voltage_v',
    'phase_a_voltage_v',
    'phase_b_voltage_v',
    'phase_c_voltage_v',
    'phase_a_current_a',
    'phase_b_current_a',
    'phase_c_current_a',
    'operating_status',
    'grid_offgrid_status',
    'operating_status_raw',
    'grid_offgrid_status_raw',
    'fault_status',
    'detailed_fault_status',
    'fault_count',
    'hardware_fault_word_1_raw',
    'hardware_fault_word_2_raw',
    'grid_fault_word_raw',
    'bus_fault_word_raw',
    'ac_capacitor_fault_word_raw',
    'system_fault_word_raw',
    'switch_fault_word_raw',
    'other_fault_word_raw',
    'active_faults',
    'fault_words_read_error',
    'igbt_temperature_c',
    'ambient_temperature_c',
    'inductance_temperature_c',
    'error',
    'logger_status',
  ];

  static const List<String> bmsTelemetryFieldOrder = [
    'timestamp',
    'sequence_no',
    'gateway_id',
    'asset_id',
    'comm_status',
    'soc_percent',
    'soh_percent',
    'rack_voltage_v',
    'rack_current_a',
    'power_kw',
    'max_cell_voltage_mv',
    'min_cell_voltage_mv',
    'cell_voltage_diff_mv',
    'max_cell_temp_c',
    'min_cell_temp_c',
    'avg_temp_c',
    'insulation_resistance_kohm',
    'positive_insulation_resistance_kohm',
    'negative_insulation_resistance_kohm',
    'precharge_stage',
    'bcu_state',
    'current_state',
    'alarm_count',
    'active_alarms',
    'logger_status',
  ];

  static const List<String> pcsEventPreferredColumns = [
    'timestamp',
    'gateway_id',
    'asset_id',
    'vendor',
    'event_type',
    'command',
    'old_value',
    'new_value',
    'readback_value',
    'source',
    'status',
    'description',
    'error',
  ];

  static const List<String> chillerEventPreferredColumns = [
    'timestamp',
    'gateway_id',
    'asset_id',
    'event_type',
    'old_value',
    'new_value',
    'source',
    'status',
    'description',
  ];

  static const List<String> errorPreferredColumns = [
    'timestamp',
    'gateway_id',
    'asset_id',
    'error_type',
    'error_source',
    'description',
  ];

  static bool isPcsAsset(String assetId) => assetId == AppConfig.pcsAssetId;
  static bool isBmsAsset(String assetId) => assetId == AppConfig.bmsAssetId;

  static List<String> telemetryFieldOrder(String assetId) {
    if (isPcsAsset(assetId)) return pcsTelemetryFieldOrder;
    if (isBmsAsset(assetId)) return bmsTelemetryFieldOrder;
    return chillerTelemetryFieldOrder;
  }

  static List<String> eventPreferredColumns(String assetId) {
    if (isPcsAsset(assetId) || isBmsAsset(assetId)) {
      return pcsEventPreferredColumns;
    }
    return chillerEventPreferredColumns;
  }

  static Set<String> defaultTelemetryFields(String assetId) {
    if (isPcsAsset(assetId)) {
      return {
        'timestamp',
        'vendor',
        'comm_status',
        'active_power_kw',
        'reactive_power_kvar',
        'power_factor',
        'frequency_hz',
        'battery_voltage_v',
        'battery_current_a',
        'dc_power_kw',
        'operating_status',
        'fault_status',
        'logger_status',
      };
    }

    if (isBmsAsset(assetId)) {
      return {
        'timestamp',
        'comm_status',
        'soc_percent',
        'soh_percent',
        'rack_voltage_v',
        'rack_current_a',
        'power_kw',
        'max_cell_voltage_mv',
        'min_cell_voltage_mv',
        'cell_voltage_diff_mv',
        'max_cell_temp_c',
        'min_cell_temp_c',
        'insulation_resistance_kohm',
        'precharge_stage',
        'bcu_state',
        'current_state',
        'alarm_count',
        'logger_status',
      };
    }

    return {
      'timestamp',
      'outlet_water_temp',
      'return_water_temp',
      'set_temperature',
      'control_mode',
      'system_on_off',
      'modbus_status',
      'logger_status',
    };
  }
}
