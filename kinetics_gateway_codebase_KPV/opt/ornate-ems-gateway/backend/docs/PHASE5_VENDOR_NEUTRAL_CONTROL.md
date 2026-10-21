# Phase 5 - Vendor-Neutral Pair Control

Phase 5 migrates the Kinetics pair-control concept to Lineage BMS + Elecod PCS without replacing the proven gateway layers around it.

## Frozen pair model

```text
Pair 1 = Lineage Rack 1 + Elecod PCS 1
Pair 2 = Lineage Rack 2 + Elecod PCS 2
Pair 3 = Lineage Rack 3 + Elecod PCS 3
Pair 4 = Lineage Rack 4 + Elecod PCS 4
```

Pair count and mapping remain configuration-driven.

## Controller selection

`app/services/control_factory.py` retains the original field-validated `BmsPcsControlService` for Kinetics assets and selects `VendorNeutralPairControlService` for Lineage + Elecod. REST routes, historian, audit, security and GatewayService therefore do not fork by vendor.

## Lineage responsibilities

The adapter exposes rack/system state, voltage/current/SOC/SOH, main-contactor feedback, insulation, dynamic maximum charge/discharge power and current, and fault reset.

The supplied V05 document does **not** provide a normal EMS precharge command/success register. Therefore the new controller does not emulate Kinetics precharge by forcing contactors. `prepare_for_operation()` observes the BMS-managed readiness state and waits for both main contactors and acceptable rack voltage.

## Elecod responsibilities

The adapter normalizes kW/kvar/PF while converting the vendor's percentage-based power setpoint internally. It owns on-grid PQ configuration, start/stop, standby, zero-power, actual power/status and setpoint readback.

Application code continues to use the gateway convention:

- discharge = positive kW
- charge = negative kW

Elecod sign semantics remain a field-validation gate before nonzero real hardware commands.

## Automatic sequence

The generic automatic sequence implements:

```text
configure PCS at 0 kW
  -> observe/enable battery readiness semantics
  -> wait for Lineage automatic DC-path readiness
  -> start Elecod PCS at zero power
  -> pair precheck
  -> calculate dynamic safe pair limit
  -> ramp requested power
  -> verify actual-power tracking
  -> start continuous runtime safety monitor
```

The pair limit is bounded by the configured gateway cap, PCS rating, Lineage rack power limit and remaining Lineage system power limit.

## Runtime safety

The runtime monitor checks communication/online state, BMS direction permission, contactor readiness, PCS running/fault/EPO state, dynamic BMS power limit and actual-power tracking. A safety violation triggers the shared safe-stop path.

## Safe stop

Default Lineage + Elecod safe stop is:

```text
command PCS zero power
 -> verify near-zero power
 -> stop PCS
 -> verify stopped
```

EMS-forced Lineage contactor opening is optional, disabled by default, blocked from the generic raw-write API, and additionally requires a separately validated field sequence.
