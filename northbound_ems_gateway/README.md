# Fast BESS Logger V2.1 Threaded Timing Patch

This patch keeps the V2 compact/value-only 90-day storage format, but fixes the observed timing issue where the configured 1-second logger was only writing around 18 rows per 60 seconds.

Root cause: the gateway's Modbus polling loop performs synchronous/blocking reads. The V2 logger ran as an asyncio task in the same event loop, so it could only run between full polling cycles. With the real deployed polling duration, the effective cadence became around 6 seconds.

V2.1 change: run the fast BESS logger in a dedicated daemon thread. It still samples only the latest values already present in AssetManager and does not add extra Modbus reads.

Expected verification result after install:

- `fast_bess_logger.execution_mode = threaded` from `/api/fast-bess/status`
- `thread_alive = true`
- `Rows added in 60 sec` should be close to `120` because 2 BESS are written every second.

The broad telemetry historian remains disabled when your existing V2 config is active:

- telemetry_snapshots should not grow rapidly
- telemetry_points should not grow rapidly
- fast_bess_samples should grow at around 2 rows/second
