#!/usr/bin/env bash
# Run this ON the i.MX93 EMS Gateway, after you've copied credentials.json
# and config.yml into the same directory. Needs root.
#
#     scp -r ems-gateway-tunnel/ root@<imx93-ip>:/tmp/
#     ssh root@<imx93-ip>
#     cd /tmp/ems-gateway-tunnel && sudo bash install_on_imx93.sh
#
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

echo "▶ 1. Downloading cloudflared (arm64 linux static binary)..."
# Latest stable arm64 binary — works on the i.MX93 (Cortex-A55 = ARMv8.2-A 64-bit)
curl -fLo /usr/local/bin/cloudflared \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64
chmod +x /usr/local/bin/cloudflared
/usr/local/bin/cloudflared --version

echo
echo "▶ 2. Installing config + credentials to /etc/cloudflared/..."
mkdir -p /etc/cloudflared
cp -v "$HERE/credentials.json" /etc/cloudflared/credentials.json
cp -v "$HERE/config.yml"       /etc/cloudflared/config.yml
chmod 600 /etc/cloudflared/credentials.json

echo
echo "▶ 3. Sanity-check that the local EMS API is up..."
for port in 8000 7000; do
  code=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 4 "http://localhost:$port/api/gateway/health" 2>/dev/null \
       || curl -sS -o /dev/null -w "%{http_code}" --max-time 4 "http://localhost:$port/api/health" 2>/dev/null \
       || echo "000")
  echo "    localhost:$port → HTTP $code"
done

echo
echo "▶ 4. Validate the tunnel config..."
cloudflared --config /etc/cloudflared/config.yml tunnel ingress validate

echo
echo "▶ 5. Install as a systemd service (so it auto-starts on boot)..."
if command -v systemctl >/dev/null 2>&1; then
  cloudflared --config /etc/cloudflared/config.yml service install || true
  systemctl daemon-reload
  systemctl enable cloudflared
  systemctl restart cloudflared
  sleep 2
  systemctl status cloudflared --no-pager | head -15
else
  echo "    no systemctl — starting cloudflared in the background instead"
  pkill -f "cloudflared.*tunnel run" 2>/dev/null || true
  nohup cloudflared --config /etc/cloudflared/config.yml tunnel run \
        >/var/log/cloudflared.log 2>&1 &
  echo "    cloudflared started, pid=$!"
  echo "    tail /var/log/cloudflared.log to watch it"
fi

echo
echo "✓ Done."
echo "  Test from anywhere:"
echo "    curl https://ems-api.unityess.cloud/api/gateway/health"
echo "    curl https://ems-logs.unityess.cloud/api/health"
