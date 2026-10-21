# Ornate EMS Gateway Platform - Architecture Freeze Candidate v1

The Kinetics field gateway remains the architectural baseline.

```text
Protocol Catalog
      |
Transport / Codec / Planner
      |
Vendor Asset Driver
      |
Normalized Asset Adapter
      |
GatewayService / Runtime Cache
      |
Pair / Plant Control
      |
Runtime Safety Monitor
      |
REST / WebSocket / Central Interfaces
      |
Historian / Alarm / Command Audit
```

## Frozen principles

1. Vendor protocols do not leak into application/control/API layers.
2. Pairing is configuration-driven: `Pair = PCS + Battery Rack`.
3. High-level power commands are in engineering units (kW/kvar), not vendor register units.
4. Safety readiness and startup are capability-driven, not hard-coded to one BMS precharge register.
5. New vendors add catalogs/drivers/adapters; they do not create a new gateway architecture.
6. New assets (meter, FSS, HVAC, DG, etc.) add asset drivers/contracts.
7. New applications (SOC control, zero export, peak shaving, TOU, grid forming) add services above normalized assets.
8. Existing APIs/storage/alarm/security behavior remains backward compatible unless explicitly versioned.

## Four-pair target

```text
Pair 1 = Elecod PCS 1 + Lineage Rack 1
Pair 2 = Elecod PCS 2 + Lineage Rack 2
Pair 3 = Elecod PCS 3 + Lineage Rack 3
Pair 4 = Elecod PCS 4 + Lineage Rack 4
```

The physical transport topology is independent of the logical pair mapping.
