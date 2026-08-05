# Kinetics Gateway Consolidated Baseline — Phase 1.6

This is a complete source baseline reconstructed in order from the running pre-Phase-1 source and the Phase 1.1 through Phase 1.6 changes. It is not an incremental patch.

## Baseline status

- Phase 1.1 through Phase 1.5: field validated and approved.
- Phase 1.6 implementation: included in full.
- Phase 1.6 formal approval: requires the packaged Phase 1.6 FRDM validation to pass on the target board.
- `bess-seven-day-v302.service`: must remain disabled and inactive during Phase 1 validation.

## Package layout

- `backend/`: complete cumulative gateway backend source through Phase 1.6.
- `phase_docs/`: release notes and FRDM validation procedures for Phases 1.1–1.6.
- `legacy_scheduler_reference/`: current external seven-day scheduler source for reference only. Do not enable it during Phases 1–4.
- `PC_AND_FRDM_USAGE.md`: safe PC update and FRDM deployment guidance.
- `SHA256SUMS.txt`: checksums for package contents.

## Phase coverage

- Phase 1.1: observability and runtime diagnostics foundation.
- Phase 1.2: process/cgroup memory attribution.
- Phase 1.3: cached reads for scheduler/status paths.
- Phase 1.4: bounded historian database locking.
- Phase 1.5: WebSocket client, send-timeout, and backpressure bounds.
- Phase 1.6: bounded two-tier HTTP admission with reserved priority capacity.

## Deliberately excluded

The archive does not contain the board virtual environment, runtime database, logs, Cloudflare credentials, Wi-Fi credentials, deployed `/etc/kinetics-gateway/config.json`, or other site secrets/runtime state. Preserve those separately from the FRDM.

## Next engineering step

After Phase 1.6 validation passes, proceed to Phase 1.7 for startup-delay and startup-memory profiling. The approximately 1.14 GiB observed baseline memory is still tracked; Phase 1.6 bounds request-related spikes but does not promise to reduce that baseline.
