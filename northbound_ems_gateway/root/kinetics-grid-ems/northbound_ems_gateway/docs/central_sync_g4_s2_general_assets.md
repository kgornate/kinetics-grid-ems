# G4 / S2 General Asset Telemetry

## Source of truth

Signal policy is generated from:

- `Central_Sync_9_Stream_Data_Contract_FROZEN_v1_1_S2_ASSET_SHEETS_20260904(1).xlsx`
- workbook SHA256: `6d17dca76d3fabbd7ffee7709a94434495c6900c1e4003f91307b923d131889c`
- source sheet: `Canonical Signal Matrix`
- active register map: `data/register_maps/unity261pv_modbus_north_v1.json`

The contract and active register map were validated point-for-point across all 1,422 canonical definitions: point ID, asset, signal, address, register count and category match exactly.

## Frozen counts

- Canonical total: 1,422
- S1 Fast BESS: 63 canonical / 126 runtime
- S2 General Asset Telemetry: 1,350 canonical / 2,700 runtime
- DO_NOT_UPLOAD: 9 canonical / 18 runtime
- Runtime total: 2,844

S2 policy counts:

- `NORMAL_5S`: 107
- `NORMAL_10S`: 357
- `NORMAL_30S`: 257
- `SLOW_60S`: 158
- `ON_CHANGE_HEARTBEAT`: 466
- `STATIC_ON_CHANGE`: 5

S2 substreams:

- `ems_system`: 93 canonical / 186 runtime
- `pcs_extended`: 242 / 484
- `bms_extended`: 726 / 1452
- `io_module`: 21 / 42
- `liquid_cooling`: 113 / 226
- `fire_protection`: 23 / 46
- `dehumidifier`: 16 / 32
- `remote_control`: 56 / 112
- `utility_meter`: 60 / 120

## Live source architecture

Normal S2 cloud flow is:

`existing gateway Modbus polling -> AssetManager live cache -> /run/nb-ems/general_asset_live.json -> GeneralAssetProducer -> G1 outbox -> uploader -> Central backend`

G4 does **not** read `nb_ems_gateway.db` as its telemetry source and does **not** poll Modbus. The only persistent database in the normal S2 delivery path is the G1 Central Sync outbox, which is intentionally used for store-and-forward delivery.

`GeneralAssetLivePublisher` runs in a dedicated gateway thread at 1 second. It publishes an atomic RAM snapshot containing exactly the 2,700 S2 runtime points selected by the frozen policy manifest. S1 and DO_NOT_UPLOAD points are excluded before the snapshot is written.

## Policy scheduler

`GeneralAssetProducer` scans the volatile snapshot every second.

- `NORMAL_5S`: periodic 5 sec
- `NORMAL_10S`: periodic 10 sec
- `NORMAL_30S`: periodic 30 sec
- `SLOW_60S`: periodic 60 sec
- `ON_CHANGE_HEARTBEAT`: startup, immediate value/quality change, then workbook-defined 30/60 sec heartbeat
- `STATIC_ON_CHANGE`: startup, immediate value/quality change, 300 sec heartbeat

Startup intentionally emits the current complete S2 state once. Thereafter only due/change/heartbeat records are enqueued.

Each logical outbox message is scoped to one S2 substream and uses envelope priority `P3`. Individual workbook priority is preserved as `signal_priority` on each signal record.

## S2 record fields

Each emitted signal record carries:

- source/runtime asset/base asset/substream identity
- stable point ID and signal name
- value, unit, category and quality
- source update timestamp and source data age
- snapshot observation time and snapshot age
- frozen policy, record cadence, upload-batch hint, signal priority and retention class
- trigger reason: `startup`, `periodic`, `change` or `heartbeat`
- `sample_source=asset_manager_live_cache`
- `persisted_source=false`

## Safety boundary

- No Modbus reads or writes are added to Central Sync.
- No control path is modified.
- Gateway field acquisition/control remains authoritative.
- Installation does not restart the gateway.
- Installation does not enable/start `central-sync.service`.
- Production `general_assets.enabled=false` until deliberate commissioning.
- A controlled gateway restart is required to load the new RAM publisher.
