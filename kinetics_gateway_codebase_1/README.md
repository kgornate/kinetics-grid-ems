# Kalpa / Ornate Local HMI — Read-only addon v0.1

**Status:** HTML/CSS/JS monitoring UI developed; HTTP/API access tests passed. **Not yet confirmed on physical HDMI monitor.**

This standalone addon should be applied to the **latest deployed Kalpa gateway tree** rather than overwriting that newer gateway with the older source snapshot used for testing. It does not alter field protocols, write/control behavior, pairing, SQLite historian, Cloudflare or Central Sync.

## Screens

At `http://<gateway>:<port>/hmi/`:

- Overview: site SOC, total active power (+ discharge / – charge for Elecod), 4 BMS/PCS pairs, alarms and connectivity.
- Battery: rack SOC/SOH, voltage/current, charge/discharge limits, state and contactors.
- PCS: running/fault/state and AC/DC telemetry per PCS.
- Alarms: live alarm table from `/api/alarms`.
- Gateway: device health and **read-only** pair control runtime status.

UI is designed for 1280 × 720 local display; it is responsive for testing on a laptop browser. It polls existing **cached** APIs every five seconds and does not initiate fieldbus reads.

## Install into the *current* gateway codebase

Run this on a development copy of your latest gateway repository first:

```bash
python install_into_gateway.py /path/to/latest/kalpa_gateway --dry-run
python install_into_gateway.py /path/to/latest/kalpa_gateway
```

The installer copies only `app/local_hmi/` and registers a read-only router in `app/main.py`. It creates backups when a router hook has to be added or an earlier HMI folder exists.

Do not copy the older reference gateway source used for addon testing over the newer Kalpa release. Apply the addon into the newer release, run that release's existing tests, and deploy during a maintenance window.

After restarting the gateway service on your development machine, open:

```text
http://127.0.0.1:8000/hmi/
```

Log in with the gateway's configured `customer` or `internal` account. Credentials are entered manually; **no JWT, password or access token is hardcoded or saved to browser storage**. Authentication is the existing `/api/auth/login`; all telemetry APIs remain JWT-protected. This is monitoring-only: there are **no power write/control controls** in the HMI.

## HDMI status / BSP dependencies

Based on the supplied FRDM logs:

- `/sys/class/drm/card0-HDMI-A-1/status`: connected
- DRM output enabled; modes include 1280x720 and 800x600
- `weston.service`: active, Weston 14.0.2
- `weston-simple-shm` processes ran without terminal errors
- `chromium` / `cog`: **not present on the FRDM image** in the supplied checks

The local browser/kiosk runtime is therefore **still a separate unresolved BSP item**. To use the HDMI display, first test that a compatible Wayland kiosk browser can be installed and can open `http://127.0.0.1:<gateway-port>/hmi/`. A normal HDMI screen without touch/keyboard will require an attended login or a separately designed secure auto-login/service-session solution. No auto-login credentials are embedded in this release.

A browser on a laptop on the gateway's local network can test the HMI now, without the HDMI runtime.

## Existing API contract reused

```text
POST /api/auth/login                 JWT login only
GET  /api/normalized/snapshot       battery_system / battery_racks / pcs / pairs / safety
GET  /api/health                    local gateway, poller and storage status
GET  /api/alarms?active_only=true   current alarms
GET  /api/control-sequence/status/all/compact  command runtime, read-only
```

No new backend database, API stream, S1–S10 producer, D1 control route or Modbus polling behavior is introduced.

## Validation

The addon was tested against the **provided `kinetics_gateway_codebase_1` source tree** (software-complete RC v0.9) using FastAPI TestClient. Total: **85 tests passed** (including the two new HMI checks). This is **not a claim that the addon has been integrated and re-tested against the latest Kalpa v0.13 Central Sync simulator release**, which was not supplied as a mounted source tree in this working turn.

Pending: actual kiosk browser/runtime and physical HDMI rendering; formal integration against the newest gateway release and UI visual acceptance test.
