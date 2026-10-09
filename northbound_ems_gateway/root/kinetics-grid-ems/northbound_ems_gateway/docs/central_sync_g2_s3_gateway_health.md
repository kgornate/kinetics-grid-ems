# Central Sync G2 - S3 Gateway Health

G2 adds the first production Central Sync producer: `gateway_health` (S3).

## Runtime path

Existing NorthBound Gateway -> authenticated loopback `/api/health` -> GatewayHealthProducer -> G1 SQLite outbox -> existing G1 uploader -> `/api/v1/ingest/batch`.

The producer performs no Modbus reads/writes and never accesses Solis serial directly.

## Behavior

- Poll local gateway health every 5 s in production (2 s in G2 test config).
- Emit startup/normal heartbeat every 30 s in production (10 s test).
- Emit a state transition immediately when transition-sensitive health changes.
- Emit an `unreachable` transition if the local gateway API becomes unavailable.
- Preserve source health timestamps returned by the gateway.
- Heartbeats use P3 by default; state transitions use P1.
- Sequences remain persistent per `(stream, substream)` through the G1 outbox.

## Stream identity

- stream: `gateway_health`
- substream: `gateway`

## Local API authentication

The producer supports either:
- `CENTRAL_SYNC_LOCAL_API_TOKEN`, or
- username from config plus password in `CENTRAL_SYNC_LOCAL_API_PASSWORD`.

Do not store plaintext local API passwords in JSON config.

## Safety

Production `central_sync.json` remains disabled after patching. The apply script only adds G2 config sections with `gateway_health.enabled=false` if absent. It does not enable/start `central-sync.service` and does not modify the EMS gateway/SOC/Solis services.
