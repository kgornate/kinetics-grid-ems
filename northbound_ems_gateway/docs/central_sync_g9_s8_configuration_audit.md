# Central Sync G9 — S8 Configuration Audit

Contract: `Central_Sync_9_Stream_Data_Contract_FROZEN_v1_3_S7_S8_RECONCILED_20260928`

## Behavior

- First successful observation baselines the current configuration and emits no historical audit event.
- Only future changes are emitted.
- Temporary loss of an optional source never creates value-to-null audit noise.
- One logical S8 message is emitted per changed setting at P1 priority.
- `audit_id` and `message_id` are deterministic for the same transition to preserve idempotency across a crash between durable enqueue and S8 state persistence.
- S8 state advances only after all detected change events are durable in the existing Central Sync outbox.
- D1 `command_poll_sec` remains absent until D1 is implemented.
- No secrets or bearer tokens are included in S8.

## Tracked settings

Controller:
- `controller.derate_soc_limit`
- `controller.derate_power_kw`
- `controller.high_limit`
- `controller.recovery_limit`
- `controller.low_cutoff_limit`
- `controller.low_recovery_limit`
- `controller.low_cutoff_enabled`

Central Sync / gateway:
- `central_sync.enabled`
- `central_sync.endpoint_url`
- `central_sync.tls_verify`
- `central_sync.fast_bess_sample_interval_sec`
- `central_sync.general_policy_revision`
- `central_sync.outbox_max_db_size_mb`
- `gateway.software_version`

Edge AI:
- `edge_ai.model_version`
- `edge_ai.threshold`
- `edge_ai.feature_count`
- `edge_ai.threshold_direction`

## Safety boundaries

G9 does not modify S1-S7 producer logic, uploader concurrency/batching, SOC controller behavior, field networking, sequence state, overflow archives, or backlog replay policy.
