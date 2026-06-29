# NorthBound EMS Gateway Architecture

## Product role

NorthBound EMS Gateway is a read-only integration bridge between an existing Chinese EMS and our local/server-side EMS stack.

It reads the EMS north-bound Modbus TCP protocol and exposes normalized local telemetry, health, alarms, and logs.

## Network roles

- `eth1`: field-side network connected to the existing Chinese EMS.
- `eth0`: application-side network for local Flutter dashboard and/or server upload.
- `wifi`: optional commissioning, debug, or backup uplink.

## Data flow

```text
Chinese EMS -> Modbus TCP read-only -> FRDM-i.MX93 Gateway -> Normalized Assets -> API/Logging/Server Upload
```

## Version 1 limits

Version 1 is strictly read-only. No writes, control APIs, schedules, setpoints, reset commands, or start/stop commands are implemented.
