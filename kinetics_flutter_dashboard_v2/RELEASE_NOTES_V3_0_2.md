# Kinetics Flutter Dashboard V3.0.2

- Uses the cache-only compact all-pair endpoint every 5 seconds.
- Tracks each active/queued pair independently every 2 seconds.
- Keeps per-pair command responses, events, busy state and run status.
- Prevents an older overview snapshot from overwriting newer pair-specific data.
- Treats queued, accepted and running states as active automatic execution.
- Displays the current runtime stage instead of Stopped Safe during queued/startup work.
- Retains direct power, next-step, abort, pair safe-stop and safe-stop-all controls.
- Production wording uses BAU 0x3001 connection/precharge.
