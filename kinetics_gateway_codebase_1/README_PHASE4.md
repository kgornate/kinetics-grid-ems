# Kalpa EMS Central Sync S2 Phase 4 — Frozen Policy + Durable 96 KiB S2

Status: **OFFLINE RELEASE FOR PHASE 5 TESTING** — NOT commissioned, NOT production validated.

## Provenance
- Gateway source archive: `kinetics_gateway_codebase_1.zip` SHA256 `0f4601db43696c7e2c8e010f283cab9535068b610e1c6fcdf89343ae17841495`.
- Frozen-policy source: `Kalpa_EMS_Central_Sync_Combined_Contract_S2_Cadence_REVIEW_v1_5.xlsx`, SHA256 `c0cb9409a01bcc4ca1a837f1fc96e31916d392b84c3ecf8bcee4541dee526540`.
- Policy manifest SHA256 `97f59c18ec78698ace04438725d3a6a68c4f65fd4be32f62cd5c8dba3284e336`.
- User freeze statement on 2026-10-15 accepted **Suggested mode** (column G) and **Suggested (s)** (column H) in all nine S2 substream worksheets. The prior workbook still displays `REVIEW`/`Pending` labels; this code treats G/H as the user-approved policy, not the labels.
- 2,471 canonical points expanded to 9,494 runtime signal instances for 4 Lineage BMS racks + 4 Elecod PCS and auxiliaries. S2.9 utility_meter currently has no configured runtime points.

## Delivered files
- `app/central_sync/s2_policy.py`: frozen manifest validation, catalog/substream drift protection, per-signal policy revision.
- `app/central_sync/s2_chunks.py`: conservative per-record UTF-8 splitter (96 KiB bound, no silent truncation).
- `app/central_sync/general_asset_producer.py`: opt-in S2 per-signal cadence engine with durable checkpoint tracking.
- `app/central_sync/outbox.py`: **additive** SQLite checkpoint table and atomic per-substream insert of bounded messages + sequences + cadence checkpoints.
- `app/central_sync/config.py`: opt-in S2 policy pathname, expected SHA256 and message cap.
- `configs/kalpa_s2_policy_frozen_v1_0.json`: exact frozen 2,471-point recording manifest.
- `configs/central_sync_kalpa_s2_frozen_v1_4_OFFLINE_TEMPLATE.json`: disabled-by-default template with pinned manifest SHA256.
- `tests/test_s2_frozen_optimized_phase4.py`: manifest validation, four-pair initial sweep, restart and cadence, failure injection, rollback, legacy fallback.

## Compatibility and scope
- **Untouched**: BMS/PCS Modbus readers and decoding, writing, pairing, EMS local safety and sequencing; S1, S3-S10, D1; backend envelope and uploader endpoints/ACK semantics.
- Default `configs/central_sync_frozen_v1_3_kalpa.json` is **unchanged**. Without an opt-in `general_assets.s2_policy_manifest_path` the original S2 path operates as before.
- The new template explicitly retains `enabled=false`, `command_downlink.enabled=false` and original site IDs. It must not be copied over a live config without a controlled deployment plan.
- New SQLite `s2_recording_checkpoint` is additive and only used by opt-in S2. No backend DB migration is required **by the patch** (backend acceptance remains to be validated in Phase 5/6).
- All S2 optimized messages are checked against an exact **98,304 byte serialized logical-message** limit before SQLite insertion; the limit is the individual JSON message, not the HTTP transport batch.
- Atomicity is per S2 substream in each producer pass: all chunks, sequences, and checkpoints for a substream either commit or roll back together. Substreams committed earlier in a pass remain committed; a failed later substream will retry on the next poll without duplicating earlier substreams.
- Checkpoints are durable (restart does not force a full first-pass replay), and their revision ties to each signal's version/mode/interval/substream. Each message retains an independent UUID and per-substream sequence.
- Change detection uses exact fingerprint of `(value, quality)` from runtime telemetry; the frozen workbook provides **no numeric analog deadbands**, so no unapproved thresholds were invented.
- Missing/unknown signals and catalog/substream drift in optimized S2 **fail closed**. This protects frozen coverage but must be explicitly checked with live device/auxiliary inventories before commissioning. S1 and local control remain separate.
- This change only controls cloud **recording**, never acquisition/polling; it does not guarantee real-time safety/event capture by itself. S4 independent critical event coverage needs Phase 5 review.

## Offline validation
From the top-level source folder with dependencies installed (`pip install -r requirements.txt pytest` in an isolated test venv):

```bash
python -m compileall -q app/central_sync
pytest -q
pytest -q tests/test_s2_frozen_optimized_phase4.py
```

Completed in this build container: **101 passed**. See `Kalpa_S2_Phase4_Offline_Test_Evidence_v1_0.json` for the synthetic 4-pair initial sweep with per-substream payload maxima. These results are NOT live MB/min measurements.

## Phase 5+ deployment gate (do NOT run on your production FRDM now)
1. Make an offline copy of the Kalpa gateway source, apply only the eight changed files at their corresponding relative paths (or use the full offline codebase ZIP), then run tests. Confirm expected SHA256 matches supplied source and manifest.
2. For offline S2 opt-in, run with `configs/central_sync_kalpa_s2_frozen_v1_4_OFFLINE_TEMPLATE.json` **after** replacing site identity, backend credentials, paths and enabling central sync only inside a test environment. No production endpoints are required for unit tests.
3. Verify the site inventory includes exactly the approved points and any new active assets have an approved policy revision before field enabling. Confirm each critical event's S4 path, uncompressed/compressed MB/min, ACK/retry behavior, WAN outage/partial-failure recovery and uploader pressure.
4. Before controlled live rollout: back up `/opt/ornate-ems-gateway/backend`, `/etc/ornate-ems-gateway`, the SQLite outbox directory, and systemd service files. Stop Central Sync before replacing source; plan a rollback for source and config, retaining SQLite durability. Never delete the outbox merely to roll back.

## Remaining Phase 5 acceptance checks
- Full timed 4-pair simulation under changing measurements, event bursts and outages.
- Actual uploader against a controlled test backend and ACK idempotency / replay testing.
- Field-normalized BMS/PCS and auxiliary point inventory coverage; verify S4 fault handling.
- Production-facing capacity, MB/min and transport pressure measurement after a controlled live integration.
