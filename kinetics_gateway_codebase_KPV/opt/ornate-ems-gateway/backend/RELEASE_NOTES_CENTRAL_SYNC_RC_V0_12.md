# Ornate EMS Gateway - Kalpa Central Sync RC v0.12

## Scope

This is a complete gateway source tree built from the latest Kalpa gateway baseline supplied for this release. The Central Sync transport/reliability architecture is reconciled against the latest Northbound EMS Gateway reference and the frozen Northbound Central Sync v1.3 backend contract.

Reference inputs used for this release:

- Kalpa baseline ZIP SHA256: `84a771d229219eb357448e21b70ebacb978d6a8b8d9b4d25a9362da01c8ecbf7`
- Northbound reference ZIP SHA256: `e11a324157e68117ebd91ba1eb973675e7d5e3c0165db96e8d62207ed0ca0b4a`
- Frozen Northbound v1.3 workbook SHA256: `d14ded3f75a380510b41d0f3911cc2b4fec52e40a72ba8776912ae38698e6cd2`

## Central Sync compatibility

S1-S9 retain the frozen Northbound stream names and backend-facing field model:

- S1 `fast_bess_telemetry`
- S2 `general_asset_telemetry`
- S3 `gateway_health`
- S4 `alarms_events`
- S5 `soc_controller`
- S6 `solis`
- S7 `edge_ai`
- S8 `configuration_audit`
- S9 `command_results`
- D1 `command_requests`

The common logical-message envelope now includes the frozen v1.3 fields `organization_id`, `record_count`, `compression`, and `gateway_software_version`. The Northbound `priority` field is retained as an additive transport hint.

S2 retains exactly the nine frozen logical partitions:

`ems_system`, `pcs_extended`, `bms_extended`, `io_module`, `liquid_cooling`, `fire_protection`, `dehumidifier`, `remote_control`, `utility_meter`.

Kalpa-specific vendor information is carried as record metadata and does not create vendor-specific cloud streams.

## New S10 application stream

S10 `battery_charge_discharge_control` is additive and intentionally new. It reports the vendor-neutral PairController runtime for the Lineage BMS + Elecod PCS BESS application. D1 remains the generic central-to-gateway request path and S9 remains the command-result ledger.

Cloud commands do not call Modbus directly. The command path is:

`Central Backend -> D1 -> Central Sync -> authenticated local gateway API -> PairController -> safety gates -> vendor drivers`.

## Reliability architecture

The release ports the mature Northbound Central Sync reliability components:

- persistent SQLite outbox with WAL
- persistent per-stream/substream sequence numbers
- gzip HTTPS batch upload
- per-message ACK handling
- retry/backoff and duplicate-safe message IDs
- priority-aware/fair batching
- overflow archive/recovery
- dynamic gateway auth with static-token fallback
- persistent D1 command ledger
- no automatic replay of a command whose field-write state became uncertain across a restart

## Validation

- Full pytest suite: **94 passed, 0 failed**
- Central Sync frozen-contract tests: **11 passed, 0 failed**
- Local Kalpa SIL gateway integration: S1, S2, S3 and S10 emitted from the real gateway REST surface; S4 and S8 correctly established first-start baselines without dumping historical events/configuration.
- S1 live SIL record count: 4 BESS/pair records.
- S2 live SIL mapping produced the frozen substreams applicable to the simulated site; `utility_meter` remained absent because no independent PCC/site meter is part of the current Lineage + Elecod protocol set.
- Fake central backend HTTP validation: gzip batch accepted; 3/3 messages ACKed; pending=0, retry=0, dead=0.
- Full Kalpa SIL producer sweep -> fake backend: **11/11 logical messages ACKed in 2 gzip HTTP requests**; included S1, S3, S10 and all applicable S2 partitions, with `bms_extended` carrying 9,020 detailed BMS records; final pending=0, retry=0, dead=0.

## Safety / field-validation status

This release is software complete for the Kalpa gateway baseline, but **Lineage + Elecod physical field validation is still pending**. Do not mark commissioning flags true solely to enable control.

Items still requiring physical confirmation include Lineage FLOAT word order, Lineage current sign, actual register offset, auxiliary Unit IDs, Elecod power sign, Elecod start/stop and ready/status behavior, low-power charge/discharge tests, and four-pair live validation.

S5/S6/S7 are compatibility slots and remain disabled unless those applications are deployed. S10 is enabled in the Central Sync producer configuration, while the Central Sync service itself remains disabled by default until backend/site commissioning.
