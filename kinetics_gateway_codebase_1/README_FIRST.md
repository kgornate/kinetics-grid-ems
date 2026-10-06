# Ornate EMS Gateway Platform - Software-Complete RC v0.9

**This archive is a complete gateway source tree. It is not a patch bundle and does not need to be copied into the old Kinetics folder.**

Keep the original `kinetics_gateway_v2_kanpur_site` snapshot frozen as the field-validated reference. Use this tree as the forward Ornate EMS Gateway platform.

## Current status

- Kinetics architecture and legacy Kinetics driver/control implementation retained.
- Lineage BMS V05 catalog, polling, alarms, system/rack/cell/auxiliary model integrated.
- Elecod Monet-AC V2.7.0 catalog, polling, status/alarm and control adapter integrated.
- Four configurable `PCS + BMS rack` pairs retained.
- Vendor-neutral staged control and automatic charge/discharge sequence implemented.
- Dynamic Lineage charge/discharge power limits enforced before Elecod power commands.
- Power ramp, tracking, runtime monitor, abort, safe-stop and safe-stop-all implemented.
- REST/WebSocket, historian, alarm lifecycle, command audit and normalized APIs retained.
- Software-in-loop four-pair validation included.
- **Real Lineage/Elecod hardware writes remain positively locked until explicit field-validation flags are confirmed.**

## Use now, before hardware arrives

```sh
cd ornate_ems_gateway
python3 -m pytest -q
python3 tools/run_elecod_lineage_sil.py
```

Primary configurations:

- `configs/elecod_lineage_4pair_sil.json` - no hardware; exercises full control path.
- `configs/elecod_lineage_4pair_phase4_readonly_template.json` - first field reads only.
- `configs/elecod_lineage_4pair_control_ready_template.json` - complete control-capable tree but all real writes/control disabled until commissioning.

## Important safety rule

Do not set protocol validation flags to `true` merely to enable control. They represent observations that must be confirmed on the physical BESS: Lineage FLOAT order/addressing/current sign/automatic precharge behavior, and Elecod addressing/power sign/start-stop/status behavior.

See:

- `docs/ARCHITECTURE_FREEZE_V2.md`
- `docs/PHASE5_VENDOR_NEUTRAL_CONTROL.md`
- `docs/PHASE6_SOFTWARE_COMPLETE_RC.md`
- `docs/FIELD_VALIDATION_GATES.md`
- `docs/MIGRATION_ROADMAP.md`
