# Ornate EMS Gateway Platform - Architecture Freeze Candidate v2

The Kinetics gateway remains the field-proven architectural baseline. The Lineage + Elecod migration demonstrates how vendor changes are isolated below stable platform contracts.

```text
Protocol Catalogs
      |
Transport / Codec / Planner
      |
Vendor Drivers
      |
Normalized Asset Adapters
      |
GatewayService + Runtime Cache
      |
Pair / Plant Controller
      |
Applications + Runtime Safety
      |
REST / WebSocket / Central Interfaces
      |
Historian / Alarm / Event / Command Audit
```

## Frozen rules

1. Vendor registers never become application API contracts.
2. `Pair = PCS + Battery Rack` is logical and configuration-driven, independent of IP/port/Unit-ID topology.
3. Plant/control code uses engineering units (kW, kvar, V, A, %, Hz).
4. Vendor-specific startup/precharge semantics belong in adapters/capabilities, not the generic pair state machine.
5. The legacy Kinetics field controller remains available for Kinetics hardware; Lineage + Elecod uses the vendor-neutral controller behind the same public routes.
6. New PCS/BMS vendors add catalogs/drivers/adapters and factory registration.
7. New assets (meter, FSS, HVAC, DG, PV, etc.) add normalized asset contracts/drivers.
8. New EMS functions (SOC control, zero export, peak shaving, TOU, grid forming, analytics) live above normalized assets.
9. Direct raw writes to safety-critical vendor points may not bypass pair-controller interlocks.
10. Unknown protocol semantics become explicit commissioning gates, never hidden software assumptions.

## Current four-pair target

```text
pair_1 -> Lineage Rack 1 + Elecod PCS 1
pair_2 -> Lineage Rack 2 + Elecod PCS 2
pair_3 -> Lineage Rack 3 + Elecod PCS 3
pair_4 -> Lineage Rack 4 + Elecod PCS 4
```

The original Kinetics topology remains supported in the same source tree.
