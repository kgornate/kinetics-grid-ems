# G3 / S1 Fast BESS Telemetry — Live Cache Source

## Frozen source path

G3 does **not** read `/mnt/ems-logs/northbound_ems_gateway/nb_ems_gateway.db` as its primary source.

Primary path:

`Modbus acquisition owned by NorthBound Gateway -> AssetManager live cache -> existing FastBESSLogger dedicated 1-second thread -> atomic volatile RAM snapshot /run/nb-ems/fast_bess_live.json -> Central Sync FastBESSProducer -> G1 durable outbox -> backend`

The local Fast BESS SQLite historian remains a parallel local-history feature only. The Central Sync outbox SQLite database remains intentionally durable because it provides store-and-forward delivery when the backend/network is unavailable.

## Live snapshot contract

The gateway publishes one atomic JSON snapshot per Fast BESS logger sample. The snapshot explicitly declares:

- `sample_source = asset_manager_live_cache`
- `persisted_source = false`
- two records: `external_ems_1` / `bess_1` and `external_ems_2` / `bess_2`
- 28 PCS scalar values per BESS
- 35 BMS scalar values per BESS
- 63 selected signals per BESS / 126 runtime values per sample
- sample timestamp, asset last-update timestamps, aggregate quality, good/bad counts, and max data age

The snapshot is atomically replaced in `/run`, so Central Sync never observes a partially-written JSON document. `/run` is expected to be volatile RAM-backed storage on the field image; commissioning should verify this with `findmnt -T /run`.

## S1 producer

Central Sync reads the volatile snapshot at a nominal 1-second cadence, rejects stale or malformed snapshots, suppresses duplicate snapshot timestamps, and enqueues one logical S1 message containing the two BESS records.

- stream: `fast_bess_telemetry`
- substream: `critical_pcs_bms`
- priority: `P2`
- expected sources: `external_ems_1`, `external_ems_2`
- expected shape: 2 BESS x (28 PCS + 35 BMS)

The producer never polls Modbus and never reads the NorthBound historian database.

## Safety

Installation does not enable or start Central Sync and does not restart the NorthBound Gateway. Production `central_sync.json` remains disabled and both `gateway_health` and `fast_bess` producers remain disabled until commissioning explicitly enables them.
