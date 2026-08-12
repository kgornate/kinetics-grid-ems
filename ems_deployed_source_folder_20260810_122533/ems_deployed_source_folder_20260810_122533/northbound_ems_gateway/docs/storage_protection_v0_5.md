# v0.5 SD Card Storage Protection

v0.5 is designed so the root filesystem does not fill because of telemetry logging.

## Protection behavior

The SQLite store checks:

- required mount path is mounted
- minimum free space is available
- DB size is below configured maximum
- retention cleanup is applied
- snapshots are stored at a slower interval than polling
- key signals are stored by default instead of all 1421 points

## Recommended field layout

```text
/root filesystem:
  OS
  gateway code
  configs
  systemd services

/mnt/ems-logs:
  SQLite DB
  WAL/SHM files
  exported CSV logs
  historian data
```

## Config

```json
"path": "/mnt/ems-logs/northbound_ems_gateway/nb_ems_gateway.db",
"required_mount_path": "/mnt/ems-logs",
"fail_if_mount_missing": true,
"min_free_space_mb": 512,
"max_db_size_mb": 2048,
"retention_days": 7,
"store_mode": "key_signals",
"snapshot_interval_sec": 30
```

## Runtime checks

```bash
df -h /mnt/ems-logs
findmnt /mnt/ems-logs
curl http://192.168.10.2:8000/api/storage/health
```

## Cleanup APIs

```text
POST /api/storage/cleanup?retention_days=7
POST /api/storage/vacuum
```

`cleanup` deletes old rows. `vacuum` physically compacts the SQLite DB file, which may take time on large databases.
