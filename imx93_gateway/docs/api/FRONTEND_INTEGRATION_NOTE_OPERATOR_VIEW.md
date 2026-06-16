# Frontend Integration Note: Operator Telemetry View

Please use the operator telemetry endpoints for dashboard telemetry grids so raw registers and storage logger fields are not shown to operators.

Recommended endpoints:

```text
GET /api/telemetry/operator
GET /api/assets/chiller_1/telemetry/operator
GET /api/assets/pcs_1/telemetry/operator
GET /api/assets/bms_1/telemetry/operator
```

Alternative query parameter style:

```text
GET /api/telemetry/latest?view=operator
GET /api/assets/{asset_id}/telemetry/latest?view=operator
GET /api/assets/{asset_id}/telemetry/keys?view=operator
GET /api/stream/telemetry?view=operator
```

The old endpoints remain unchanged and still return full engineering/debug telemetry:

```text
GET /api/telemetry/latest
GET /api/assets/{asset_id}/telemetry/latest
```

Operator view hides noisy fields like `storage_logger`, raw registers, `*_raw`, `raw_*`, register arrays, and binary fault bit dumps. It keeps operator-useful values such as temperature, pressure, SOC, power, status, alarms, fault code, and fault description.
