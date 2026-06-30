# NorthBound Flutter Dashboard v0.4.1 - Asset API Shape Fix

## Issue

Gateway v0.5 returns the asset catalog as:

```json
{
  "items": [
    {"asset_id": "bms_1", "display_name": "BMS 1"}
  ]
}
```

Earlier Flutter parsing expected:

```json
{
  "assets": [...]
}
```

or:

```json
{
  "assets": {
    "bms_1": {...}
  }
}
```

Because of that mismatch, the dashboard displayed:

```text
Invalid /api/assets response: assets must be a list or map
0 cards
```

## Fix

`NorthboundApiClient.getAssets()` now supports all known shapes:

```text
assets list
assets map
items list
items map
data list/map fallback
```

`NorthboundApiClient.getAlarms()` was also updated to support gateway v0.5 alarm shape:

```json
{
  "active_count": 0,
  "items": []
}
```

as well as older:

```json
{
  "alarms": []
}
```

## Gateway changes required

No gateway change is required. This is a Flutter compatibility patch.

## Expected result

After v0.4.1, `GET /api/assets` with v0.5 gateway should again render all 9 cards.
