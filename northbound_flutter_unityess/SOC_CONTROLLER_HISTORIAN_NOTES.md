# SOC Controller Historian - 2026-08-30

The existing SOC Control page now includes a full historian-style query panel using the gateway's existing `/api/controller/history` endpoint.

## Added

- Quick ranges: 15 min, 1 hour, 6 hours, 24 hours, 7 days.
- Custom From / To date + time selection.
- Event filters: All, Solis, BESS, Settings, Errors.
- Load limits: 100, 500, 1000 events.
- Oldest-first / latest-first ordering.
- Client-side table pagination: 25, 50, 100 rows/page.
- Full-range paginated loading through 1000-event API pages.
- 50,000-event Flutter-side full-range safety cap.
- Cancel button for long full-range fetches.
- CSV export of loaded filtered controller history.
- XLSX export of loaded filtered controller history.
- Table fields include controller state, X/Y SOC, Solis state/power, target, result and message.

## Gateway usage

No new gateway endpoint is required. The Flutter client now passes `from_time` and `to_time` to the already-existing:

`GET /api/controller/history`

Full-range loading uses the endpoint's existing `limit` + `offset` pagination.

## Live status behavior

The SOC/Solis live status cards continue to refresh independently every 5 seconds. A custom historical query is no longer overwritten by the live polling loop.
