# Stage 4.1 control-cache compatibility fix

The Stage 4 read-only test confirmed that repeated `fresh=true` polling was removed. It also exposed a payload compatibility issue:

- `GET /api/control-sequence/{pair}/status?fresh=false` returns the compact automatic-run runtime state only.
- The Flutter control screen requires the complete cached control snapshot: pair metadata, summary telemetry, blockers, workflow, runtime, write gates, refresh source and timestamp.

Stage 4.1 therefore changes normal visible-screen polling to:

`GET /api/diagnostics/runtime-monitor/{pair}/sample`

This endpoint uses the Stage 3C shared background-poll cache and does not perform direct BMS/PCS live reads. Existing protections remain unchanged:

- one control-status request at a time;
- one collapsed pending refresh maximum;
- polling only while the Control screen is visible;
- no automatic retries of write commands;
- control buttons remain blocked whenever cached readiness data is unavailable or unsafe.

No gateway write sequence, sign convention, power limit, or control confirmation phrase is changed.
