# Kinetics Gateway Phase 1.2 — Process and Cgroup Memory Attribution

Baseline: Phase 1.1 observability patch validated on the FRDM i.MX93 on
2026-08-05.

## Purpose

The 30-minute Phase 1.1 observation showed a stable Python RSS near 101 MiB but
systemd `MemoryCurrent` near 1.0 GiB. Phase 1.2 attributes that difference before
any memory limit, allocator tuning, cache change, polling change, or control
refactor is attempted.

## Scope

This patch extends the existing internal-only endpoint:

`GET /api/diagnostics/runtime`

New `process.breakdown` fields report anonymous, file-backed, shared, private,
PSS and swap memory when the Linux procfs fields are available.

The new `cgroup` section reports:

- cgroup-v2 path, current and peak memory;
- cgroup swap usage;
- cgroup process, thread and PID counts;
- bounded `memory.stat` categories (anonymous, file cache, kernel, page tables,
  sockets, shared memory and slab);
- bounded memory pressure/OOM event counters.

Unsupported or inaccessible kernel files produce `available: false` or `null`
fields; diagnostics remain operational.

## Safety boundary

No changes were made to Modbus addresses, drivers, register values, polling
intervals, control sequencing, pair mapping, safety predicates, scheduler
policy, historian schema, telemetry payloads or service startup behavior.

The external scheduler remains intentionally disabled for this diagnostic
phase.

## Changed files

- `backend/app/services/runtime_metrics.py`
- `backend/tests/test_runtime_metrics.py`
- `PHASE1_2_RELEASE_NOTES.md`
- `PHASE1_2_FRDM_VALIDATION.md`

## Decision rule

Do not add `MemoryMax`, clear caches, change SQLite behavior, or tune polling
until the FRDM samples show whether the cgroup difference is mainly file cache,
anonymous memory, kernel/slab memory, or additional cgroup processes.
