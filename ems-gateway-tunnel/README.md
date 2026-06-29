# EMS Gateway Cloudflare Tunnel — i.MX93 setup

Run cloudflared **on the i.MX93 itself**. The device tunnels outbound to
Cloudflare; no LAN routing dependency on the Mac Mini, no IP-change
brittleness, works on mobile hotspots / Wi-Fi / Ethernet identically.

## What's in this folder

| File | Purpose |
|------|---------|
| `credentials.json` | Tunnel credentials. **Secret.** Don't commit, don't share. |
| `config.yml` | Cloudflared config — maps `ems-api.unityess.cloud → :8000` + `ems-logs.unityess.cloud → :7000`. |
| `install_on_imx93.sh` | One-shot installer that downloads cloudflared, copies these files into `/etc/cloudflared/`, and starts it as a systemd service. |

## Tunnel & domains

| Item | Value |
|------|-------|
| Tunnel name | `ems-gateway` |
| Tunnel ID   | `6bf7b93d-1005-40d3-aabf-bf1348085c6d` |
| Public REST + SSE | `https://ems-api.unityess.cloud`  → `http://localhost:8000` on the i.MX93 |
| Public logs API   | `https://ems-logs.unityess.cloud` → `http://localhost:7000` on the i.MX93 |

## Run on the i.MX93

From the Mac Mini, copy this folder to the device:

```bash
# Find the i.MX93 IP first (e.g. 10.55.41.131)
scp -r /Users/ornateserver/portals/ems-gateway-tunnel/ root@<imx93-ip>:/tmp/
ssh root@<imx93-ip>
cd /tmp/ems-gateway-tunnel
sudo bash install_on_imx93.sh
```

That's it. The script:

1. Downloads `cloudflared` (arm64 static binary, ~30 MB).
2. Installs config + credentials to `/etc/cloudflared/`.
3. Pings local ports 8000 + 7000 to make sure the EMS APIs are alive.
4. Installs cloudflared as a systemd service that auto-starts on boot.

## Verify from anywhere (laptop, phone, the dashboard team's laptops)

```bash
curl https://ems-api.unityess.cloud/api/gateway/health
curl https://ems-api.unityess.cloud/api/assets
curl https://ems-api.unityess.cloud/api/telemetry/latest

# SSE live stream
curl -N https://ems-api.unityess.cloud/api/stream/telemetry

# Logs server
curl https://ems-logs.unityess.cloud/api/health
```

No VPN, no static IP, no port forwarding. Works the same regardless of
which Wi-Fi/hotspot the device is on.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `connection refused` from public URL | Local API isn't running on port 8000 / 7000 on the device. Restart the EMS service. |
| Public URL returns 502 | Cloudflared can reach the device but the local API isn't responding. Same fix. |
| Public URL returns 530 / 1033 | `cloudflared` isn't running on the device. `systemctl status cloudflared`, `journalctl -u cloudflared -n 50`. |
| Need to change the routed ports | Edit `/etc/cloudflared/config.yml` on the device, then `sudo systemctl restart cloudflared`. |
| Want to revoke the tunnel | On the Mac Mini: `cloudflared tunnel delete ems-gateway`. |
