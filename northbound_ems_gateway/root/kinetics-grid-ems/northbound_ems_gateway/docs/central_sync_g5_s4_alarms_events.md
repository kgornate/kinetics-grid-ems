# Central Sync G5 — S4 Alarms & Events

## Contract

Source: `Central_Sync_9_Stream_Data_Contract_FROZEN_v1_1_S2_ASSET_SHEETS_20260904.xlsx`

Sheets:
- `S4 Alarms Events`
- `S4 Event Trigger Catalog`
- `Retention Priority Rules`

Frozen event-capable catalog:
- 342 canonical trigger signals
- 2 EMS runtime sources
- 684 runtime trigger instances
- 315 candidates from S2 live general-asset telemetry
- 27 candidates from S1 Fast BESS telemetry

## Architecture

S4 performs no Modbus reads, no NorthBound historian reads and no local HTTP calls.

```
AssetManager cache
  -> existing RAM snapshots
     /run/nb-ems/general_asset_live.json
     /run/nb-ems/fast_bess_live.json
  -> S4 transition detector
  -> Central Sync durable outbox
  -> existing Central Sync uploader
  -> /api/v1/ingest/batch
```

## Event semantics

A runtime signal is compared against the frozen vendor enumeration semantics in
`data/central_sync/s4_event_trigger_catalog_frozen_v1_1.json`.

- inactive -> active: emit `ACTIVE`
- active -> inactive: emit `CLEARED`
- active code A -> active code B: emit another `ACTIVE` in the same correlation lifecycle
- same state/value: suppress

The producer persists compact lifecycle state in:

`/var/lib/nb-ems-central-sync/s4_event_state.json`

This prevents Central Sync restarts from re-emitting identical active alarms.
On the first deployment only, already-active alarm states are emitted once when
`startup_emit_active=true`, so the backend receives current safety state.

## S4 record

Each record follows the frozen S4 contract:

- event_id
- correlation_id
- timestamp_utc
- gateway_id
- site_id
- source_id
- asset_id
- signal_name
- event_type
- severity
- state
- previous_value
- current_value
- message
- controller_state
- decision
- payload
- dedupe_key
- occurrence_count
- cleared_at_utc

## Priority

- Critical -> P0
- High -> P1
- Warning -> P2
- Info -> P3

A poll cycle produces at most one S4 logical message. If multiple simultaneous
transitions exist, the message uses the highest priority among its records.

## Safety / isolation

S1, S2 and S3 are unchanged.
The new producer only consumes their existing live RAM source snapshots.
The main NorthBound gateway service does not need to be modified or restarted.

## G4.1/G4.2 compatibility hardening

This deployment bundle is specifically compatible with the validated G4.1 reliability
and G4.2 throughput baseline. S4 outbox sequence/enqueue/stats operations are offloaded
from the asyncio event loop, `OutboxCapacityError` is handled as producer backpressure,
and the G4.2 `outbox.py`/`uploader.py` files are not replaced.

The compact S4 lifecycle state file is persisted on first baseline and on actual state
transitions, not rewritten every 1-second steady-state poll. This avoids unnecessary
eMMC write amplification while retaining restart deduplication.
