# API Connectivity

The gateway listens on `0.0.0.0:8000`, so the same REST and WebSocket API is reachable through every correctly configured FRDM network interface.

| Path | Example base URL | Use |
|---|---|---|
| Direct Ethernet from PC to FRDM eth0 | `http://192.168.10.2:8000` | Local commissioning and Flutter testing |
| FRDM Wi-Fi address | `http://<mlan0-ip>:8000` | Local Wi-Fi clients on a reachable network |
| Cloudflare hostname | `https://<kinetics-hostname>` | Remote Flutter and IT/backend access |

The Cloudflare ingress entry must point to `http://127.0.0.1:8000` for the Kinetics gateway service. The tunnel must also allow WebSocket upgrades for `/ws/telemetry` and `/ws/alarms`.

The gateway serves the data; it does not automatically push it into an external IT database. IT systems can consume:

- REST snapshots and asset endpoints
- Delta WebSocket telemetry
- Alarm WebSocket or REST alarm APIs
- Historian and CSV export APIs

The API contract and authentication are identical on LAN, Wi-Fi, and Cloudflare. Only the base URL changes.
