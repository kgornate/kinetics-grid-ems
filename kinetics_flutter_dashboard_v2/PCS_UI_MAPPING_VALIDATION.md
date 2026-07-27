# PCS UI Mapping Validation

Validated against the uploaded live gateway snapshot and PCS protocol workbook.

## Detected RTU devices

| Asset | Unit ID | Online | Telemetry points |
|---|---:|---|---:|
| PCS 1 | 1 | True | 288 |
| PCS 2 | 2 | False | 0 |
| PCS 3 | 3 | False | 0 |
| PCS 4 | 4 | False | 0 |

## PCS 1 fields used by the dashboard

| Field | Live value | UI section |
|---|---:|---|
| Operating state | 1.0 | Overview / Operating status |
| Product mode | 1 | Overview / Operating status |
| PQ mode | 0 | Overview / Operating status |
| DC bus voltage | 0.1 V | Overview / DC side |
| Grid AB voltage | 796.9000000000001 V | Overview / AC-Grid |
| Grid frequency | 50.02 Hz | Overview / AC-Grid |
| Active power | 0.0 kW | Overview / AC-Grid |
| IGBT A temperature | 27.0 â | Overview / Thermal |
| Cabinet temperature | 44.900000000000006 â | Overview / Thermal |

The Flutter release remains read-only.