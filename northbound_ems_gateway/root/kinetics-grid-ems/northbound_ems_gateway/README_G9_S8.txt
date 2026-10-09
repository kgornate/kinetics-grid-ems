G9 / S8 CONFIGURATION AUDIT PATCH
Baseline: gateway_complete_code_20261006T063641Z.tar.gz
Baseline SHA256: 59d43a4dc81a49f5e1569acaaf44e986e5b7d23aff14393da6caddf9e54d6e91
Contract: Central Sync 9-Stream FROZEN v1.3 S7/S8 reconciled

Adds S8 configuration_audit only. S1-S7 behavior, G6.4 single-worker uploader,
SOC logic, networking, sequences, overflow protection and replay policy are not changed.

S8 first startup creates a baseline only and emits no fabricated history.
Future changes are emitted as P1 configuration_audit events.
Backlog replay remains disabled.
