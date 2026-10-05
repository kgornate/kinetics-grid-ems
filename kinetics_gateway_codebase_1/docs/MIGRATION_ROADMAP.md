# Kinetics -> Elecod + Lineage Migration Roadmap

| Phase | Deliverable | Hardware status |
|---|---|---|
| 1 | Kinetics codebase/feature/architecture study | No new runtime code |
| 2 | Register dependency + feature-parity matrix | No new runtime code |
| 3 | **Actual migrated codebase begins**: catalogs, protocol support, normalized adapters, config scaffolding, tests | Safe/read-only template; not site-commissioned |
| 4 | **DONE in v0.2** - Lineage + Elecod live polling integrated end-to-end into existing APIs/history/alarms + normalized cached views + read-only commissioning tooling | Hardware read-only commissioning |
| 5 | Four-pair start/stop/charge/discharge controller on normalized adapters | Guarded writes + low-power commissioning |
| 6 | Full feature parity, automatic four-pair operation, safe-stop, deployment, field validation | Production release / architecture freeze |

## Rule

A Kinetics feature remains part of the target unless the new hardware protocol makes it genuinely unavailable. Hardware differences change adapter implementation, not the gateway architecture.
