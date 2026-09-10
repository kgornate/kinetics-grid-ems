# UGX Cloud Uploader U1.3 Combined POST Mode

U1.3 changes the UGX uploader from separated cloud POSTs to a combined-post model.

## Problem solved

U1.2 could send different telemetry profiles as separate POST requests to the same UGX endpoint:

- Fast 41-key BESS profile
- 60-second PCS/BMS profile
- 300-second or 900-second slow profile

This was still a single UGX API endpoint, but it created multiple POST requests over time. UGX requested that due payloads should be clubbed into a single request where possible.

## U1.3 behavior

U1.3 gathers all due profiles inside the gateway process and sends one timestamped-array payload to the same UGX telemetry endpoint per upload window.

Default production-safe configuration:

- One cloud POST window: 60 seconds
- Fast 41-key BESS records: buffered and included in the next combined POST
- 60-second PCS/BMS profile: included when due
- 300-second slow profile: included when due
- 300-second profile reuses the UGX 900-second key group through `frequency_key_aliases: {"300": 900}`
- 3600-second cell-level heavy profile remains disabled
- Old full PCS/BMS snapshot path remains disabled

## Payload format

The payload remains compatible with UGX telemetry API:

```json
[
  {"ts": 1786620000000, "values": {"stack_volt": 870.2, "rack_soc_r1": 65.7}},
  {"ts": 1786620060000, "values": {"stack_soh": 100, "arrsoe": 75.3}},
  {"ts": 1786620300000, "values": {"cluprechgvol_r1": 855.9}}
]
```

## Expected request-rate impact

Before U1.3, a 10-minute audit showed 65 successful UGX POSTs. U1.3 should reduce the normal cloud request rate to approximately one POST per minute, so around 10 POSTs per 10 minutes, while carrying the fast records and due frequency records inside the same request.

## Important clarification

U1.3 does not change the cloud endpoint. It still uses only:

```text
POST https://platform.uniqgrid.com/api/v1/EMSTEST/telemetry
```

Localhost calls to `127.0.0.1:8000` are internal gateway reads and do not hit UGX.
