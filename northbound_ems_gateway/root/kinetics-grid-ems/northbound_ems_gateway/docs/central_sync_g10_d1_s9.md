# G10 — D1 Command Downlink + S9 Command Results

Frozen source basis: post-G9/S8 commissioned gateway.

## Safety architecture

Backend command queue -> D1 poller -> gateway validation/idempotency/expiry -> authenticated loopback Gateway API -> existing ControlService -> S9 durable outbox -> existing single fair uploader -> backend ACK.

D1 never writes Modbus directly. Existing `routes_control.py`, `routes_commands.py`, Pydantic request validation, `internal_admin` authorization, ControlService, protocol write/readback and device safety paths remain authoritative.

## Frozen D1 queue schema used

Required fields: `command_id`, `gateway_id`, `site_id`, `issued_at_utc`, `expires_at_utc`, `requested_by`, `requested_role`, `command_type`, `arguments`, `requires_readback`, `priority`. `note` is optional.

Allowed initially: `source_grid_mode`, `site_grid_mode`, `source_charge`, `source_discharge`, `source_standby`, `site_power`, `site_standby`, `ems_register_write`, `ems_batch_write`.

`solis_on_off` remains blocked pending a separate safety review.

## S9

One immutable terminal result per command is emitted to `command_results/gateway` at P0. Fields follow the frozen S9 contract, including validation, execution timestamps, write/readback, verification, final status, error code and duration.

## Idempotency / crash safety

A separate SQLite ledger at `/mnt/ems-logs/northbound_ems_gateway/d1_command_ledger.db` suppresses duplicate `command_id` values across restarts. A command left in an uncertain executing state after a crash is never automatically re-executed; it is failed safe with `COMMAND_RECOVERY_UNCERTAIN` and an S9 result.

## Backend D1 HTTP contract

The frozen spreadsheet defines D1 queue semantics but does not freeze a URL. The gateway implementation uses a configurable path, default `/api/v1/commands/poll`, and D1 remains disabled until the backend endpoint is commissioned.

Expected request:

`GET /api/v1/commands/poll?gateway_id=<id>&site_id=<id>&limit=<n>` using the same gateway Bearer authentication as Central Sync ingest.

Expected no-work response: HTTP 204, or HTTP 200 with `{"commands": []}`.

Expected work response: HTTP 200 with `{"commands": [<D1 command objects>]}`.

Delivery should be at-least-once. Backend may keep a command durable until it receives a terminal S9 result. Gateway duplicate suppression prevents repeated field execution.

## Commissioning

The first production test must use `tools/central_sync_d1_s9_inject.py --expired-safe-test`. It generates an already-expired `source_standby` D1 command. The gateway must reject it as `COMMAND_EXPIRED`, make zero local-control calls/field writes, enqueue S9, and receive normal backend ACK through the existing uploader.
