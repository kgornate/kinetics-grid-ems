# Kinetics Gateway Phase 1.5 — WebSocket Backpressure

Baseline: Phase 1.4 passed on the FRDM i.MX93 on 2026-08-05 with the external
scheduler disabled and inactive.

## Scope

- Delta telemetry remains the default.
- Full telemetry streaming is disabled by default.
- Telemetry and alarm sockets share a configurable eight-client limit.
- Every JSON send has a configurable two-second deadline.
- Slow clients are disconnected with WebSocket code 1013.
- Runtime diagnostics count rejected clients, send timeouts and backpressure disconnects.

The deployed JSON configuration does not need to change because all new settings
have safe defaults. No Modbus driver, catalog, control service, pair mapping,
scheduler policy, historian schema or polling interval is changed.

## Changed files

- `backend/app/core/config.py`
- `backend/app/api/routes.py`
- `backend/app/services/runtime_metrics.py`
- `backend/tests/test_api.py`
- `backend/tests/test_runtime_metrics.py`
- `backend/tests/test_scheduler_storage.py` (includes the Phase 1.4 test-schema correction)

## Acceptance

- focused suite passes with 17 tests;
- normal Flutter delta telemetry stays connected and refreshing;
- `mode=full` is rejected with code 4403;
- WebSocket runtime counters are present;
- health remains responsive under Flutter traffic;
- no service restart, warning, OOM or scheduler activation occurs.
