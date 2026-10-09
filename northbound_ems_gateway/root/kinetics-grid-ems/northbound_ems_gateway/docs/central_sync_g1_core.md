# Central Sync G1 Core

G1 adds the Central Sync reliability/transport foundation without changing the existing Modbus gateway process.

## Added components

- `src/nb_ems_gateway/central_sync/config.py` - standalone Central Sync configuration.
- `contracts.py` - frozen logical message envelope and transport batch wrapper.
- `outbox.py` / `sequence.py` - durable SQLite outbox and persistent per-stream/substream sequence counters.
- `batcher.py` - priority-aware coalescing and request size/message limits.
- `client.py` - persistent HTTPX HTTPS client, optional gzip, gateway Bearer token.
- `uploader.py` - partial ACK, `already_processed`, retry/backoff/jitter, 413 splitting, Retry-After handling.
- `status.py` - atomic status JSON file.
- `service.py` - independent `central-sync.service` process.
- `tools/central_sync_mock_server.py` - local mock IT backend.
- `tools/central_sync_enqueue_test.py` - synthetic outbox producer for G1 tests.

## Non-goals in G1

G1 has no S1-S9 production producer and performs no Modbus reads or writes. G2 adds S3 Gateway Health. G3 adds S1 Fast BESS from the existing historian.

## Reliability rule

A producer persists a logical message to SQLite before network transfer. The backend must ACK a message only after durable commit. Local data is marked `acked` only for `accepted` or `already_processed` per-message ACK status.
