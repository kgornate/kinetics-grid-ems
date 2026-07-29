# Kinetics Gateway V2.6 — Multi-pair runtime monitoring

## Purpose

This patch allows independent Rack/PCS pairs to remain energized while another
pair starts, ramps, or is selected in the Flutter application.

The original controller already stored sequence threads, abort events, monitor
threads, safe-stop locks, and runtime state per pair. The defect was in live
status scheduling: when a running pair's runtime monitor needed a live fallback
and the single global refresh lane was occupied, `global_refresh_lane_busy` was
handled as a generic monitor exception. The generic exception path performed a
physical safe-stop.

## Corrected safety behaviour

A busy refresh lane is now classified as **verification deferred**, not as a
hardware fault.

1. The runtime monitor first consumes the background BMS/PCS polling cache.
2. When that cache is incomplete or stale, the monitor joins a fair FIFO queue
   for the serialized live-refresh lane and waits a bounded time.
3. Temporary lane contention or a transient live-read failure is recorded and
   retried.
4. If fresh verification recovers inside the grace window, the pair continues.
5. If the pair remains unverifiable longer than the configured limit, the
   gateway performs a fail-safe stop.
6. Real safety violations still stop immediately: E-stop/hard fault, open BMS
   contactors, open PCS DC breaker, BMS direction prohibition, unavailable rack
   current limit, or a dynamic BMS limit below the active command.

Default settings:

```json
{
  "runtime_monitor_refresh_wait_seconds": 10.0,
  "runtime_monitor_max_unverified_seconds": 30.0
}
```

The unverified limit must be greater than or equal to the lane wait time.

## New cache-only overview API

```text
GET /api/control-sequence/status/all
```

The shared live-refresh lane is still one-at-a-time, as required for the fieldbus,
but FIFO ordering prevents a startup sequence from repeatedly jumping ahead of
already-waiting runtime monitors.

The response contains `pairs`, `by_pair_id`, and a summary of active, starting,
and failed pairs. It never performs a direct Modbus read, so Flutter overview
polling cannot compete with automatic sequences or safety monitoring.

## Runtime observability

Runtime state and diagnostics now expose:

- `monitor_state`
- `monitor_verification_deferred`
- `monitor_unverified_since`
- `monitor_unverified_seconds`
- `monitor_last_warning`
- `monitor_last_verified_at`
- deferred-verification and recovery counters per pair

Diagnostic endpoint:

```text
GET /api/diagnostics/runtime-monitor
```

## Automatic-start response

HTTP 202 now explicitly means **request accepted**. It does not mean target
power has already been reached. Completion requires the pair runtime to show
that the automatic sequence completed and its monitor is active.

## Validation included

The source package includes automated tests for:

- temporary refresh contention recovering without safe-stop;
- prolonged loss of verification causing fail-safe stop;
- cache-only all-pair overview;
- busy refresh lane conversion into deferred verification;
- existing control, catalog, storage, and API behaviour.

This software has passed the included backend unit tests. It still requires
low-power validation on the actual i.MX93/BMS/PCS installation before normal
multi-pair operation.
