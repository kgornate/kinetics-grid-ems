# Kinetics EMS Gateway V3.0.0

## Field-derived production correction

This release replaces the experimental per-BCU precharge write with the BMS vendor-confirmed production path:

| Pair | BMS TCP port | BAU unit | BCU unit | Production connect/cut-off |
|---|---:|---:|---:|---|
| Pair 1 | 503 | 1 | 2 | BAU `0x3001`: `1=connect`, `2=cut off` |
| Pair 2 | 504 | 1 | 2 | BAU `0x3001`: `1=connect`, `2=cut off` |
| Pair 3 | 505 | 1 | 2 | BAU `0x3001`: `1=connect`, `2=cut off` |
| Pair 4 | 506 | 1 | 2 | BAU `0x3001`: `1=connect`, `2=cut off` |

BCU `0x0018=3` and the positive/negative contactor bits in `0x001F` remain the authoritative precharge completion feedback. BCU `0x0402` is retained only as an optional diagnostic read and is never written by production control.

## Main changes

- Pair-specific BAU assets route writes to ports 503-506 instead of a global port-503 bank.
- Independent Pair 1-4 startup, charging, discharging, direct setpoint, automatic ramp, abort and safe-stop.
- Pair safe-stop verifies zero setpoint, zero actual power and PCS stopped before BAU cut-off.
- `Safe Stop All` processes enabled pairs sequentially and preserves pair isolation.
- Cache-only all-pair status endpoint with aggregate setpoint, actual power and active/faulted pair counts.
- Canonical top-level control status for cached and live reads; no nested workflow snapshot selection.
- Per-pair refresh locks plus a fair single live-hardware lane protect the shared RS485 transport.
- Runtime monitor uses bounded cache verification with live fallback and fail-safe timeout.
- Bounded in-memory update buffer and pair maps prevent unbounded UI/gateway memory growth.

## Power convention

- Negative kW: charging
- Positive kW: discharging
- Project software cap: 240 kW per pair, additionally limited by live BMS current/power limits.
