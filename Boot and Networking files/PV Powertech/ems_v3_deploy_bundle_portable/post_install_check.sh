#!/usr/bin/env bash
set -euo pipefail

echo "== EMS V3 post-install checks =="
echo
systemctl list-dependencies ems-v3-app-stack.target | grep -E 'ems-v3-gateway|ems-v3-soc-controller|ems-v3-solis-link|cloudflared|ems-v3-wifi|ems-v3-eth1' || true

echo
echo "[Current service states]"
for svc in ems-v3-eth1.service ems-v3-wifi.service cloudflared.service ems-v3-solis-link.service ems-v3-gateway.service ems-v3-soc-controller.service ems-v3-app-stack.target; do
  printf '%-32s %s
' "$svc" "$(systemctl is-enabled "$svc" 2>/dev/null || true) / $(systemctl is-active "$svc" 2>/dev/null || true)"
done

echo
echo "[Interfaces]"
ip -br addr show eth0 2>/dev/null || true
ip -br addr show eth1 2>/dev/null || true
ip -br addr show mlan0 2>/dev/null || true

echo
echo "[Routes]"
ip route 2>/dev/null || true

echo
echo "[Solis link]"
ls -l /dev/ems_solis_rtu /dev/ttyUSB0 2>/dev/null || true

echo
echo "[Local API checks]"
for url in http://127.0.0.1:8000/api/health http://127.0.0.1:7000/api/health; do
  code="$(curl -s -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || true)"
  echo "$url -> HTTP ${code:-000}"
done
