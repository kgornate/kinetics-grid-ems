# Northbound EMS — S2 v1.4 Cadence + Bounded Logical Message Splitting

**Status: OFFLINE TESTED — NOT FOR FIELD DEPLOYMENT**  |  Prepared 15 Oct 2026.

## Authoritative inputs

- Gateway: `northbound_gateway_FULL_DEPLOYMENT_20261009T092346Z.tar(3).gz` (user-confirmed source of truth).
- Frozen Excel: `Central_Sync_9_Stream_Data_Contract_v1_4_S2_CADENCE_FROZEN_20261014.xlsx`.
- Prior offline v1.4 cadence patch remains incorporated in this package.

## Operational changes — only TWO files

1. `data/central_sync/canonical_signal_policy_frozen_v1_1.json`: 1,350 S2 policy cadence changes; all 72 non-S2 policy records retained unchanged. File *name deliberately unchanged* to match existing source/config paths. The contents and manifest SHA change, requiring both live gateway publisher and Central Sync to reload the same version at cutover.
2. `src/nb_ems_gateway/central_sync/general_asset_producer.py`: recognizes `PERIODIC`; splits S2 records into **bounded logical messages per substream**, each with a normal independent message_id and next_sequence; retains the same `LogicalMessage` and `TransportBatch` schema. Does not add chunk-number fields or change stream/substream names. Keeps per-signal producer state correctly committed after successful enqueue even if later chunks encounter outbox-capacity backpressure.

**Unmodified**: uploader, outbox/SQLite schema, backend client, backend contracts, S1/S3-S9 producers, register maps, device Float decoding, SOC/control logic, and service configuration.

## Byte budget

Configured live uploader `max_request_bytes=131072` (128 KiB). This S2 producer constrains each *logical message* to `min(96 KiB, floor(0.75 × configured uploader max_request_bytes))` using exact UTF-8 JSON byte lengths. It performs a complete preflight before committing any chunks of a snapshot. A single unchunkable record is rejected safely with a visible error and no new sequence consumed. Message counts increase but record counts and per-record JSON fields stay unchanged.

**IMPORTANT**: This is a **logical-message cap, not a global hard HTTP-request cap**. Outbox batching still uses its previous advisory 128 KiB target, can group messages, and can send existing historical oversized rows. The existing HTTP 413 request bisection only works when a request contains multiple logical messages. Test representative live/archived data with the real backend before any field rollout.

## Offline results (synthetic data; both EMS sources)

- Startup: **2,700 point records, 25 S2 logical messages** rather than nine; **12 BMS Extended chunks**.
- Largest new logical message: **98,268 bytes**; largest single-message transport wrapper: **98,412 bytes**.
- At synthetic t=60s: **1,310 records / 15 messages**.
- The simulated SQLite + real uploader + fake ACK backend stayed below the 128 KiB advisory limit in recorded batches; this is **not** a backend guarantee.
- Verified: no lost/duplicated signal records at startup, same per-substream sequence namespace, all IDs unique; 60s scheduling, change/quality transitions, bad manifest-hash rejection, interruption after 3 chunks followed by clean recovery, single oversize-record preflight, adaptive smaller uploader budget, SQLite persistence, partial ACK retry, HTTP 413 bisection and `already_processed` ACK support.
- Unchanged model: **31.0833 S2 signal-values/sec quiet-period**, down **81.4%** from the earlier frozen contract. Chunking increases the *number of logical envelopes* (therefore may slightly increase MB/min) without affecting the signal cadence or values/sec.

## Validate, but DO NOT install

Use an OFFLINE extracted copy of the October 9 gateway source. Nothing below touches a field board.

```bash
python3 verify_patch_against_baseline.py /path/to/offline_oct9_gateway
```

Make a SECOND disposable offline copy and overlay the two `patch_files/` paths onto it; from this patch folder run:

```bash
S2_TEST_GATEWAY_ROOT=/path/to/disposable_patched_gateway python3 test_s2_bounded.py
```

Dependencies: the baseline gateway's `pydantic`/`httpx` Python environment.

## Outstanding production gates — NO DEPLOY until resolved

1. Real backend must accept **multiple same-substream messages for a single snapshot timestamp** and idempotently ACK each `message_id` and sequence. Existing outbox sorts some same-timestamp candidates by random `message_id` rather than per-substream sequence, so verify **out-of-order sequence acceptance** or coordinate ordering policy with backend.
2. Verify backend's **per-request byte limit, maximum records/message**, partial/per-message ACK, missing ACK/retry, and HTTP 413 response for representative BMS bursts. This package uses a fake backend; it is not an end-to-end live test.
3. Confirm the 128 KiB advisory request limit is sufficient for actual mixed-stream batches, and assess any existing older oversized outbox/archive messages separately; this patch **does not retroactively split historical messages**.
4. Test with representative *real* RAM snapshots (including quality/missing values, large numeric/string values, and on-change float noise), and validate S4 alarm transition coverage and S8 audit requirements.
5. Validate CPU load and SQLite write/burst behavior on an offline i.MX93 equivalent, coordinate gateway publisher and Central Sync manifest SHA cutover, and prepare backups / rollback without modifying existing backlog.
6. Measure actual new-payload MB/min and HTTP ACK throughput for 24h; the previous **~1.3–1.8 MiB/min all-stream target remains an estimate** and may slightly increase due to chunk envelope overhead.

**No production gateway, production database, field network or backend was accessed or modified.**
