# Kinetics Gateway Phase 1.4 — Historian/Cache-Lock Separation

Baseline: Phase 1.3 passed on the FRDM i.MX93 on 2026-08-05 with the external
scheduler disabled and inactive.

## Purpose

Telemetry finalization previously invoked JSON preparation, compression and
SQLite historian writes while holding the gateway's global cache lock. A slow
SD-card write could therefore delay health, monitoring, WebSocket and cached
control-status reads even though those readers did not require the historian.

## Changes

- A due historian interval is claimed under the cache lock.
- A bounded historian payload is copied under that lock.
- JSON encoding, compression and SQLite batch insertion run only after the
  cache lock is released.
- BMS and PCS polling retain their existing synchronous write durability: a
  poll worker still observes historian write failures.
- Historian statistics are updated under a short cache-lock section only after
  persistence completes.
- A regression test blocks SQLite persistence and verifies that a cached rack
  summary remains immediately available.

## Safety boundary

No Modbus operation, register, polling interval, control sequence, safety
predicate, pair mapping, scheduler policy, historian schema, sampling interval,
retention rule, API response schema, authentication rule or WebSocket payload
format is changed.

## Changed files

- `backend/app/services/gateway_service.py`
- `backend/tests/test_scheduler_storage.py`
- `PHASE1_4_RELEASE_NOTES.md`
- `PHASE1_4_FRDM_VALIDATION.md`

## Pass criteria

- the new lock-separation regression test passes;
- the Phase 1 focused suite passes;
- gateway remains active with `NRestarts=0`;
- historian-write count continues increasing with zero errors;
- health latency remains below 500 ms during historian activity;
- no warning-level gateway journal entries occur;
- scheduler remains disabled and inactive; no control commands are issued.
