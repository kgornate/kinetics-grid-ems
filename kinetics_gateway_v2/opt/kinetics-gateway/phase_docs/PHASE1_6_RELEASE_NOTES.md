# Kinetics Gateway Phase 1.6 — Bounded HTTP Admission

Phase 1.6 is an incremental patch over the formally approved Phase 1.5 baseline.

## Changes

- Bounds all admitted HTTP work to 12 concurrent requests.
- Limits ordinary dashboard, historian, export, and telemetry traffic to 8 concurrent requests.
- Reserves 4 slots for health, login, runtime diagnostics, control, and control-sequence requests.
- Rejects excess work after 100 ms with HTTP 503 and `Retry-After: 1`.
- Adds bounded runtime counters for accepted, active, peak, and rejected work by lane.
- Adds unit tests for capacity, reserved priority, path classification, and metrics.

## Safety and compatibility

- No Modbus transport, register, polling, historian, pair, sequence, or scheduler logic changes.
- No deployed JSON configuration change is required; defaults are backward compatible.
- WebSocket traffic remains governed independently by the approved Phase 1.5 policy.
- The external scheduler must remain disabled and inactive during validation.

## Default policy

```text
http_max_concurrent_requests = 12
http_reserved_priority_requests = 4
general HTTP capacity = 8
http_admission_timeout_seconds = 0.10
```

