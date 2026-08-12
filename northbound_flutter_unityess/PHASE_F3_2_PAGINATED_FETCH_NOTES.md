# Phase F3.2 - Historian Custom Date/Time + Paginated Full-Range Fetch

This patch builds on Phase F3.1 Historian export final patch.

## Added

- Quick range and custom date/time range modes.
- Exact From date/time and To date/time selection using Flutter date/time pickers.
- Table-only load for quick viewing using the selected row limit.
- Full selected range loading for export using paginated 5000-row API calls.
- Progress display while full-range data is being fetched.
- Cancel button for long full-range loads.
- Table pagination so large loaded datasets do not render all rows at once.
- CSV and Excel export now export all loaded rows, not just the currently visible table page.

## Intended usage

For viewing: use **Load table only** with a small/medium table limit.

For export: select the exact date/time window, click **Load full range for export**, wait for the load to complete, then click **Download CSV** or **Download Excel**.

## Safety limits

Flutter-side full-range loading is capped at 250,000 rows. This is enough for a full 24-hour raw export for both BESS:

- 2 BESS rows/second x 86,400 seconds = 172,800 rows/day

For 7/30/90-day raw exports, use a backend/downsampled export in a future phase because raw data becomes too large for browser/desktop UI memory and Excel sheet limits.

## Gateway load behavior

Full-range export does not request the whole range in one gateway call. It fetches bounded pages:

- 5000 rows per API request
- 120 ms pause between pages
- ascending time-cursor pagination using timestamp_epoch_ms

This keeps gateway requests bounded and avoids one heavy direct export from the gateway.

## Validation

1. Open Historian.
2. Select Quick range or Custom date/time.
3. Click Load table only and verify limited table load.
4. Click Load full range for export and watch progress.
5. Verify table page controls: Previous page, Next page, Rows/page.
6. Download CSV and Excel.
7. Confirm exported file contains all loaded rows, not only visible rows.
