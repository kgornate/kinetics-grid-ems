# G11 Central Sync Store-and-Forward Recovery

## Objective

Keep S1-S8 producers and durable local persistence running even when backend transport is intentionally paused or Internet/backend connectivity is unavailable. Once transport recovers, live data is uploaded first and overflow segments are replayed automatically without enabling the legacy historical backlog replayer.

## Runtime behavior

Normal:

`S1-S8 producers -> live SQLite outbox -> single live uploader -> backend ACK`

Transport paused or backend unavailable:

`S1-S8 producers -> live SQLite outbox -> overflow archiver -> central_sync_overflow_*.db`

Recovery:

`live uploader drains current traffic -> overflow recovery yields to live health -> same single transport lock -> backend ACK`

## Important operational rule

Do not use `systemctl stop central-sync.service` when the requirement is only to stop backend upload. Stopping the whole service also stops S1-S8 producers.

Use:

```sh
bash tools/central_sync_transport_control.sh pause backend_maintenance
bash tools/central_sync_transport_control.sh status
bash tools/central_sync_transport_control.sh resume
```

The pause file is `/var/lib/nb-ems-central-sync/uploader.pause`.

## Safety invariants

- S1-S8 remain enabled.
- Live uploader worker count remains 1.
- Live and overflow-recovery HTTP requests share one `asyncio.Lock`, so only one backend request is active from this Central Sync process at a time.
- Legacy `central-sync-backlog-replay.service` remains disabled/inactive.
- Automatic recovery only scans `central_sync_overflow_*.db`; it does not touch `central_sync_backlog_*.db` historical archives.
- Overflow recovery yields when live queue count/age, memory, or load are outside configured gates.
- Drained overflow DB files are retained and marked with `.replayed.json`; they are not auto-deleted.
- If a retained hourly overflow DB later receives new rows, DB/WAL signature changes invalidate the marker and recovery resumes.
- Existing sequence numbers, outbox, retry/backoff, fair batching, ACK processing and overflow copy-before-delete semantics are preserved.

## Default recovery gates

- recovery enabled: true
- request pause: 10 s
- replay batch: 25 messages
- replay soft request target: 128 KiB
- pause recovery when live unacked > 25
- pause recovery when live oldest age > 3 s
- minimum available memory: 500 MB
- maximum load1: 2.0

These gates make live traffic higher priority than recovered overflow traffic.

## Scope limitation

This patch prevents future Central Sync capture gaps caused by backend outages or an operator transport pause. It cannot recreate Central Sync messages from an interval where the entire `central-sync.service` had previously been stopped; reconstruction of such historical gaps would require stream-specific local-history reconstruction and is intentionally outside G11.
