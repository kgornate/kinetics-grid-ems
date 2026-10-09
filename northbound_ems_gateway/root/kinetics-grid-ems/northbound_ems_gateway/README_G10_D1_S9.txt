G10 D1/S9 gateway-side patch.

- Based on commissioned post-G9/S8 source.
- Does not modify outbox.py or uploader.py.
- Preserves S1-S8, sequences, single uploader worker and backlog replay OFF.
- Adds D1 persistent idempotency ledger and S9 terminal results.
- D1 production polling is installed DISABLED because the live backend command endpoint is not yet exposed.
- First live test is an expired command with zero field execution.
