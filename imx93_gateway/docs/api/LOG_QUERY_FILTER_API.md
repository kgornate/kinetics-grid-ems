# Log Query and Filter API

The gateway keeps the existing log HTTP API behavior while moving filter logic into a structured storage query layer.

## Existing endpoints preserved

```text
GET /api/logs/assets
GET /api/logs/files?asset_id=pcs_1
GET /api/logs/telemetry?asset_id=pcs_1&date=YYYY-MM-DD&limit=100
GET /api/logs/events?asset_id=pcs_1&event_type=PCS_ACTIVE_POWER_WRITE&status=success&limit=100
GET /api/logs/errors?asset_id=bms_1&error_type=communication&source=modbus&limit=100
GET /api/logs/metadata
GET /api/logs/download/telemetry?asset_id=pcs_1&date=YYYY-MM-DD
```

## Supported telemetry filters

```text
asset_id
asset/date
start_time
end_time
fields
limit
offset
order
search
modbus_status
logger_status
vendor
comm_status
operating_status
fault_status
communication_status
bcu_state
current_state
```

Example:

```bash
DATE=$(date +%F)
curl -s "http://127.0.0.1:7000/api/logs/telemetry?asset_id=pcs_1&date=$DATE&fields=timestamp,active_power_kw,dc_voltage_v&start_time=10:00&end_time=12:00&limit=50" | python3 -m json.tool
```

## Supported event filters

```text
asset_id
date
start_time
end_time
fields
limit
offset
order
search
event_type
status
source
vendor
command
```

Example:

```bash
curl -s "http://127.0.0.1:7000/api/logs/events?asset_id=pcs_1&event_type=PCS_ACTIVE_POWER_WRITE&status=success&limit=50" | python3 -m json.tool
```

## Supported error filters

```text
asset_id
date
start_time
end_time
fields
limit
offset
order
search
error_type
error_source
source
```

`source` is accepted as a backward-compatible alias for `error_source`.

Example:

```bash
curl -s "http://127.0.0.1:7000/api/logs/errors?asset_id=bms_1&error_type=communication&source=modbus&limit=50" | python3 -m json.tool
```

## Internal architecture

```text
HTTP query parameters
        |
        v
LogFilter
        |
        v
LogQueryService
        |
        v
CSVLogQueryBackend
        |
        v
CSV log files
```

This keeps CSV behavior intact while making the query layer portable to future storage backends such as SQLite or cloud storage.
