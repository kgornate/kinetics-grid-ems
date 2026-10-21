# Kalpa Central Sync backend handoff

## Backend expectation

Reuse the existing Northbound `/api/v1/ingest/batch` implementation and S1-S9 database model. Kalpa identifies itself through `gateway_id`, `site_id`, `organization_id`, asset IDs, vendor metadata and signal IDs; it does not require alternate S1-S9 wire schemas.

The only new uplink schema requiring backend extension is:

- S10 `battery_charge_discharge_control`

The existing D1 queue schema is reused. Kalpa adds PairController-oriented command types; the queue fields themselves are unchanged.

## Provisioning values to set before site enablement

- real `gateway_id`
- real `site_id`
- real `organization_id`
- production backend `base_url`
- TLS verification/trust configuration
- gateway authentication client ID/secret or approved bearer-token mechanism
- local gateway internal API credential/token

Do not store secrets in the JSON template committed to the source tree. Use the provided environment-variable mechanism.

## Activation order

1. Keep `central_sync.enabled=false` during image preparation.
2. Provision identity/backend credentials.
3. Start local EMS gateway and verify read-only asset telemetry.
4. Run `python -m app.central_sync.service --config configs/central_sync_frozen_v1_3_kalpa.json --dry-contract`.
5. Enable Central Sync uplink and verify S1/S2/S3/S4/S8 ACKs from staging backend.
6. Verify S10 ingest independently.
7. Keep D1 disabled until backend identity/RBAC/expiry/idempotency and local commissioning gates are accepted.
8. Enable D1 only during controlled commissioning.

## Expected site capability behavior

S5 SOC Controller, S6 Solis and S7 Edge AI are emitted only when those applications exist and are explicitly enabled. Their absence at Kalpa is not a Central Sync fault.

S2 `utility_meter` remains empty until an independent site/PCC meter is integrated.

## Remaining physical validation

Backend compatibility is a software concern and is validated in this release. Physical commissioning remains separate: Lineage decoding/sign/address details and Elecod command/status behavior must be confirmed on the real Kalpa BESS before production control enablement.
