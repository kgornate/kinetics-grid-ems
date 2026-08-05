# Kinetics Gateway Phase 1.3 — Cached Read Paths and Non-Blocking Startup

Baseline: Phase 1.2 passed on the FRDM i.MX93 under normal Flutter monitoring
load on 2026-08-05.

## Purpose

Phase 1.2 measured 2–3 second responses from health and diagnostic endpoints,
PCS polling near four seconds, and peak event-loop lag near two seconds. This
patch removes avoidable full-snapshot, compression and live-storage work from
monitoring requests. It does not tune or change fieldbus polling.

## Changes

- `/api/health` now reads bounded cached counters and cached storage state.
- `/api/diagnostics/polling` reads polling counters directly.
- `/api/diagnostics/data-rate` returns a cached analysis refreshed off-loop.
- `/api/storage/status` returns cached status.
- New `/api/bms/racks/summary` omits large rack telemetry maps.
- Initial telemetry warm-up runs in a worker after FastAPI becomes available.
- Periodic pollers start only after warm-up completes, avoiding duplicate
  startup fieldbus traffic.
- Startup readiness/error information is exposed as `health.startup`.

## Safety boundary

No control sequence, Modbus register, driver, point catalog, polling interval,
pair mapping, scheduler policy, historian schema, authentication rule,
WebSocket format, or existing API field was intentionally changed.

## Changed files

- `backend/app/main.py`
- `backend/app/api/routes.py`
- `backend/app/services/gateway_service.py`
- `backend/tests/test_scheduler_storage.py`
- `PHASE1_3_RELEASE_NOTES.md`
- `PHASE1_3_FRDM_VALIDATION.md`

## Pass criteria

- focused tests pass;
- gateway becomes active and remains at `NRestarts=0`;
- `health.startup.ready` becomes true;
- cached health/polling/data-rate/storage/rack-summary requests return 200;
- their ten-sample maximum latency is below 500 ms under local Flutter load;
- no HTTP, background, WebSocket, OOM or service-restart errors occur;
- scheduler remains disabled and inactive; no control commands are issued.
