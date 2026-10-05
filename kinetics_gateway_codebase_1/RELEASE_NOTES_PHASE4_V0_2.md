# Ornate EMS Gateway - Elecod + Lineage Phase 4 v0.2

## Purpose

Complete read-only gateway codebase for first live integration of Lineage BMS V05 and Elecod Monet-AC PCS V2.7.0 while preserving the field-validated Kinetics gateway architecture.

## Major changes from Phase 3

- Lineage `system_rack` topology integrated into `GatewayService`.
- One Lineage system/BAMS read per cycle instead of four duplicate pair-bank reads.
- Rack 1..4 polling integrated into the existing fast/normal/slow/bulk scheduler.
- Configurable Lineage auxiliary endpoints by category and Unit ID.
- Auxiliary polling disabled by default until vendor/site Unit-ID allocation is confirmed.
- Elecod polling uses the shared protocol planner and honors each point's Modbus read function.
- Vendor-neutral cached battery/PCS/pair snapshot added without extra fieldbus reads per API request.
- Lineage FC02 system/rack alarms integrated into the existing alarm lifecycle.
- Read-only commissioning APIs/tooling added.
- New Ornate service/install entry points added while historical Kinetics deployment files remain for reference.
- `ORNATE_EMS_*` credential environment variables supported with Kinetics compatibility fallback.
- Runtime database/log artifacts removed from the release source package; storage is created at runtime.

## Safety state

- `mode=read_only`
- BMS writes disabled
- PCS writes disabled
- Pair control disabled
- Automatic sequence disabled
- Elecod active-power sign not marked validated

## Automated regression

`69 passed, 0 failed`

## Next phase

Phase 5 will migrate `BmsPcsControlService` onto normalized Lineage/Elecod adapter capabilities and enable guarded low-power start/stop/charge/discharge only after Phase-4 live-read commissioning is complete.
