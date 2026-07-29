# Stage 4 Flutter stability patch

This source patch is designed for the Stage 3A/3B/3C gateway backend.

## Changes

- Normal control status polling now always uses `fresh=false`.
- Control status requests are single-flight; overlapping timer/manual/post-command refreshes collapse into one active request plus one pending cached refresh.
- Control polling runs only while the Control navigation destination is visible.
- Leaving Control, logout and disposal cancel the polling timer.
- Pair changes ignore late responses from the previously selected pair.
- A second control POST is rejected locally while one command is in progress.
- The UI displays cache source, stale/fresh status, status timestamp and whether visible-screen polling is active.
- Control status timeout is 10 seconds; command POSTs are not automatically retried.
- Conservative commissioning defaults are 0 kW target, 0.5 kW ramp step and 5 second ramp interval. Operators must enter the intended target deliberately.
- Safe-shutdown text now matches the selected-BCU control sequence and the gateway runtime-monitor quiesce patch.

## Important

The included Windows build output from the original archive was intentionally removed from this source release because it predates this patch. Rebuild on Windows with `build_windows_release.ps1` before operator deployment.
