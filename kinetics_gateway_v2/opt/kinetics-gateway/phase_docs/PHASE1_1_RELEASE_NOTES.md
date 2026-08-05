# Kinetics Gateway Phase 1.1 — Observability and Request Accounting

Baseline: `frdm_kinetics_running_snapshot_20260804_231509.tar.gz`

Baseline SHA-256: `312b2b376673c22ca1cb8348b13c97b6a4d12e7c0e1486e50958717e9c0119d8`

## Scope

This patch is additive observability only. It does not change Modbus addresses,
register values, scaling, control sequencing, safety predicates, pair mapping,
scheduler policy, telemetry response contracts, historian schema, or audit schema.

Added measurements:

- Process RSS and peak RSS
- OS thread count
- asyncio task count and peak
- Current and peak in-flight HTTP requests
- Per-route count, errors, slow count, average/max/last latency
- Last 20 slow requests (bounded memory)
- Poll/background duration, errors, and missed cycles
- Historian write duration and errors
- WebSocket accepted, active, disconnected, peak, and send-failure counts
- Event-loop lag and peak lag

The new internal-only endpoint is:

`GET /api/diagnostics/runtime`

It requires the existing internal role. Existing API payloads are unchanged.

## Changed files

- `backend/app/main.py`
- `backend/app/api/routes.py`
- `backend/app/services/gateway_service.py`
- `backend/app/services/runtime_metrics.py` (new)
- `backend/tests/test_api.py`
- `backend/tests/test_runtime_metrics.py` (new)

## Protected-file verification

The following live baseline files remain byte-identical:

- `app/services/bms_pcs_control.py`
- `app/assets/bms_driver.py`
- `app/assets/pcs_driver.py`
- `generated_protocols/bms_catalog.json`
- `generated_protocols/pcs_catalog.json`
- `scheduler/bess_seven_day_v302_compatible_scheduler.py`

## Verification status

- Python compile check: passed
- RuntimeMetrics direct smoke checks: passed
- Changed-file scope comparison: passed
- Protected control/register checksum comparison: passed
- Full pytest suite: must run on the FRDM Python 3.13 virtual environment
- Hardware/control test: not required for this observability-only patch

Do not progress to Phase 1.2 until the FRDM test suite passes and the gateway
completes an initial observation period with dashboard and WebSocket traffic.
