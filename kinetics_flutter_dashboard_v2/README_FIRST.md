# Kinetics Gateway V2.6 multi-pair runtime patch

This is a focused update for the currently deployed Kinetics Gateway backend.
It does not contain the database, logs, Cloudflare credentials, authentication
secrets, or an entire filesystem snapshot.

## Corrected behaviour

- Each BMS/PCS pair retains independent sequence and runtime-monitor state.
- Live control refresh remains serialized, but waiting requests use FIFO order.
- `global_refresh_lane_busy` is treated as temporary deferred verification.
- A running pair is not stopped solely because another pair is starting.
- A pair still safe-stops on a real safety violation or when its status cannot
  be verified for longer than the configured grace period.
- Flutter/SCADA can poll all pairs through the cache-only endpoint:
  `GET /api/control-sequence/status/all`.

## Deployment prerequisite

Before installing, physically verify all four pairs are safely stopped:

- PCS setpoint = 0 kW
- actual power = 0 kW
- PCS stopped
- BMS precharge idle
- positive and negative contactors open

The installer itself sends no BMS or PCS command.

## Install on i.MX93

```sh
cd /root/kinetics_gateway_v2_6_multi_pair_runtime_patch
sh deployment/update_multi_pair_runtime_v2_6_on_imx93.sh
# The first call changes nothing and prints the required confirmation.
sh deployment/update_multi_pair_runtime_v2_6_on_imx93.sh APPLY_MULTI_PAIR_V2_6
```

A timestamped backup is created under `/root/` before any runtime file changes.

## Rollback

```sh
sh deployment/rollback_multi_pair_runtime_v2_6_on_imx93.sh \
  /root/kinetics_multi_pair_v2_6_backup_TIMESTAMP \
  ROLLBACK_MULTI_PAIR_V2_6
```

Confirm all pairs are safely stopped before rollback.
