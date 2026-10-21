# Kinetics -> Elecod + Lineage Migration Roadmap

| Phase | Deliverable | Status |
|---|---|---|
| 1 | Study and freeze the actual Kinetics architecture/feature baseline | DONE |
| 2 | Kinetics -> Elecod/Lineage feature and register dependency matrix | DONE |
| 3 | Full source-tree migration foundation: catalogs, protocol support, adapters, config scaffolding | DONE |
| 4 | Lineage + Elecod live read path into cache, alarms, history, APIs and normalized pair views | DONE in software; field reads pending hardware |
| 5 | Vendor-neutral four-pair start/stop/charge/discharge, dynamic limits, ramp, runtime monitor, safe-stop | DONE in software/SIL |
| 6 | Full feature-parity RC, deployment gates, architecture freeze candidate, field-validation plan | SOFTWARE-COMPLETE RC; physical BESS validation pending |
| 7 | Read-only + staged low-power + fault/safe-stop field validation | Pending BESS availability |
| 8 | Production v1.0 field-validated freeze | Pending Phase 7 |

## Development rule

The gateway is now one platform source tree. Future vendor changes should add or modify drivers/adapters/configuration, not create a separate gateway architecture.
