# Kalpa Central Sync compatibility with frozen Northbound v1.3

## Compatibility objective

The central backend/database already developed for the Northbound EMS Gateway remains the contract authority for S1-S9. Kalpa must adapt at the gateway edge rather than require a second backend parser.

## Frozen common message envelope

Every logical uplink message emitted by Kalpa contains:

- `schema_version`
- `message_id`
- `gateway_id`
- `site_id`
- `organization_id`
- `stream`
- `substream`
- `sequence`
- `created_at_utc`
- `record_count`
- `records[]`
- `compression`
- `gateway_software_version`

`priority` is retained as an additive Northbound transport hint. `record_count` is validated against `len(records)` before insertion into the persistent outbox.

## S1-S9 stream freeze

| ID | Stream | Kalpa action |
|---|---|---|
| S1 | `fast_bess_telemetry` | Lineage/Elecod normalized pair data adapted to Northbound per-BESS fast record shape |
| S2 | `general_asset_telemetry` | Detailed Lineage/Elecod point records adapted to frozen S2 record shape and nine substreams |
| S3 | `gateway_health` | Frozen gateway/source/storage/OS/service/Central Sync health model |
| S4 | `alarms_events` | Frozen event fields; first installation establishes cursor instead of historical flood |
| S5 | `soc_controller` | Frozen compatibility slot; disabled unless application exists |
| S6 | `solis` | Frozen compatibility slot; disabled unless application exists |
| S7 | `edge_ai` | Frozen compatibility slot; disabled unless application exists |
| S8 | `configuration_audit` | Frozen audit fields and tracked Central Sync/gateway configuration paths |
| S9 | `command_results` | Frozen command execution/result ledger |
| D1 | `command_requests` | Frozen command queue envelope; Kalpa adds PairController command types |

## Frozen S2 substreams

Kalpa does not introduce vendor-specific wire partitions. S2 uses exactly:

1. `ems_system`
2. `pcs_extended`
3. `bms_extended`
4. `io_module`
5. `liquid_cooling`
6. `fire_protection`
7. `dehumidifier`
8. `remote_control`
9. `utility_meter`

Lineage cells, pack data and rack data remain records inside `bms_extended`. Elecod detailed PCS points remain inside `pcs_extended`. Vendor/address/function-code details are additive metadata on the point record.

`utility_meter` is reserved and currently emits no Kalpa records because the current protocol set does not include an independent PCC/site utility meter.

## S10 additive application

`battery_charge_discharge_control` is a new application stream and is not part of the frozen Northbound S1-S9 contract. It reports PairController requested/commanded/actual power, direction, BMS readiness/limits, PCS run state, safety blocks, application state, and platform readiness.

D1 requests and S9 results remain separate from S10 runtime reporting.

## Command safety

Central Sync never writes a Modbus register directly. Supported Kalpa D1 command types are translated only into authenticated local API operations:

- `pair_precheck`
- `pair_automatic_start`
- `pair_set_power`
- `pair_zero_power`
- `pair_safe_stop`
- `pair_abort`
- `safe_stop_all`

The local PairController remains the control/safety authority. The persistent command ledger prevents duplicate execution and refuses to replay an uncertain write after restart.
