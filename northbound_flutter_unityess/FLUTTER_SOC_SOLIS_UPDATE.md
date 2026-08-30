# SOC / Solis Flutter Operator Integration

This build integrates the gateway-side automatic SOC/Solis controller into the existing Strategy page, which is now labelled **SOC Control** in the top navigation.

## Added operator features

- Live automatic-controller state and human-readable decision.
- BESS X SOC, online state and automatic target state.
- BESS Y SOC, online state and automatic target state.
- Solis ON/OFF state, online state, active power and automatic target state.
- Controller LIVE/DRY-RUN and healthy/error indication.
- Current high/recovery/low/low-recovery SOC thresholds.
- Automatic control-state table.
- Persistent controller/Solis/BESS event history with filters.
- Current controller communication/cycle error surfaced to the operator.
- Existing EMS strategy/command readback retained under an expandable section.

## Role behaviour

- `customer_admin`: read-only controller status, history and threshold values.
- `internal_admin`: same read view plus **Edit thresholds**.
- Threshold writes use `PATCH /api/admin/controller/settings`; the API remains the security authority and rejects non-internal users.

## Gateway APIs used

- `GET /api/controller/status`
- `GET /api/controller/history`
- `GET /api/controller/settings`
- `PATCH /api/admin/controller/settings` (internal admin only)
- Solis status/history methods are also available in the API client for future dedicated screens.

## Runtime behaviour

The SOC Control page polls the gateway every 5 seconds. A threshold save is persisted by the gateway and takes effect on the next controller cycle; no Flutter-side logic attempts to control BESS or Solis directly.
