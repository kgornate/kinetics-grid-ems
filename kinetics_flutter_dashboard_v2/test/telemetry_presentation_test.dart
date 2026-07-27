import 'package:flutter_test/flutter_test.dart';
import 'package:kinetics_gateway_dashboard/core/presentation/telemetry_presentation.dart';
import 'package:kinetics_gateway_dashboard/models/gateway_models.dart';

void main() {
  test('rack per-mille SOC is displayed as percent', () {
    const point = TelemetryPoint(value: 927, raw: 927, unit: '‰', quality: 'good');
    final shown = presentPoint('bms_rack', 'soc', point);
    expect(shown.text, '92.7 %');
  });

  test('energy meter U32 payload is decoded as float32', () {
    const point = TelemetryPoint(value: 1131118655, raw: 1131118655, unit: 'V', quality: 'good');
    final shown = presentPoint('energy_meter', 'essmeter_1_1', point);
    expect(double.parse(shown.value), closeTo(235.5, 0.1));
  });

  test('mojibake temperature unit is normalized', () {
    const point = TelemetryPoint(value: 23.3, raw: 233, unit: 'â', quality: 'good');
    final shown = presentPoint('bms_rack', 'tcell_max', point);
    expect(shown.text, '23.3 °C');
  });

  test('PCS operating-state bit mask is presented as an engineering state', () {
    const point = TelemetryPoint(value: 1, raw: 1, quality: 'good');
    final shown = presentPoint('pcs', 'operating_state', point);
    expect(shown.value, 'Stop');
  });

  test('PCS product and PQ modes are presented in English', () {
    const product = TelemetryPoint(value: 1, raw: 1, quality: 'good');
    const pq = TelemetryPoint(value: 0, raw: 0, quality: 'good');
    expect(presentPoint('pcs', 'actual_product_mode', product).value, 'PQ mode');
    expect(presentPoint('pcs', 'actual_pq_mode', pq).value, 'Constant power');
  });
}
