#!/bin/sh
# ==========================================================
# NorthBound EMS Gateway status printer
# Safe to run manually or from /etc/profile.d after SSH login.
# ==========================================================

CONFIG_FILE="/etc/nb_ems_gateway.conf"
[ -f "$CONFIG_FILE" ] && . "$CONFIG_FILE"

NB_EMS_GATEWAY_DIR="${NB_EMS_GATEWAY_DIR:-/root/kinetics-grid-ems/northbound_ems_gateway}"
NB_EMS_GATEWAY_CONFIG="${NB_EMS_GATEWAY_CONFIG:-configs/development.json}"
NB_EMS_GATEWAY_MOCK="${NB_EMS_GATEWAY_MOCK:-1}"
NB_EMS_GATEWAY_API_PORT="${NB_EMS_GATEWAY_API_PORT:-8000}"
NB_EMS_GATEWAY_START_LOG="${NB_EMS_GATEWAY_START_LOG:-/var/log/nb_ems_gateway_start.log}"
PUBLIC_API_URL="${PUBLIC_API_URL:-https://ems-api.unityess.cloud}"

printf '\n'
printf '======================================\n'
printf 'NorthBound EMS Gateway Status\n'
printf '======================================\n'
printf 'Config file       : %s\n' "$CONFIG_FILE"
printf 'Gateway folder    : %s\n' "$NB_EMS_GATEWAY_DIR"
printf 'Gateway config    : %s\n' "$NB_EMS_GATEWAY_CONFIG"
printf 'Mock mode         : %s\n' "$NB_EMS_GATEWAY_MOCK"
printf 'Local API port    : %s\n' "$NB_EMS_GATEWAY_API_PORT"
printf 'Public API URL    : %s\n' "$PUBLIC_API_URL"

printf '\n[Service status]\n'
if command -v systemctl >/dev/null 2>&1; then
    systemctl is-active nb-ems-gateway.service >/dev/null 2>&1 && printf 'nb-ems-gateway.service : ACTIVE\n' || printf 'nb-ems-gateway.service : NOT ACTIVE\n'
    systemctl is-active ems-network-setup.service >/dev/null 2>&1 && printf 'ems-network-setup     : ACTIVE\n' || printf 'ems-network-setup     : NOT ACTIVE\n'
    systemctl is-active cloudflared >/dev/null 2>&1 && printf 'cloudflared           : ACTIVE\n' || printf 'cloudflared           : NOT ACTIVE\n'
else
    printf 'systemctl not available\n'
fi

printf '\n[Port check]\n'
ss -lntp 2>/dev/null | grep ":$NB_EMS_GATEWAY_API_PORT" || printf 'No process currently listening on port %s\n' "$NB_EMS_GATEWAY_API_PORT"

printf '\n[Local API health]\n'
LOCAL_CODE="$(curl -sS -o /tmp/nb_local_health.json -w '%{http_code}' --max-time 3 "http://127.0.0.1:$NB_EMS_GATEWAY_API_PORT/api/health" 2>/dev/null || echo 000)"
printf 'http://127.0.0.1:%s/api/health -> HTTP %s\n' "$NB_EMS_GATEWAY_API_PORT" "$LOCAL_CODE"
if [ "$LOCAL_CODE" = "200" ]; then
    if command -v python3 >/dev/null 2>&1; then
        python3 - <<'PY' 2>/dev/null || true
import json
p='/tmp/nb_local_health.json'
try:
    d=json.load(open(p))
    print('gateway_mode     :', d.get('gateway_mode') or d.get('mode') or d.get('status'))
    print('asset_count      :', d.get('asset_count'))
    print('online_assets    :', d.get('online_asset_count'))
    print('total_signals    :', d.get('total_signal_count'))
    print('bad_signals      :', d.get('bad_signal_count'))
    print('commands_enabled :', d.get('commands_enabled'))
except Exception:
    pass
PY
    fi
fi
rm -f /tmp/nb_local_health.json

printf '\n[Cloudflare public API health]\n'
PUBLIC_CODE="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "$PUBLIC_API_URL/api/health" 2>/dev/null || echo 000)"
printf '%s/api/health -> HTTP %s\n' "$PUBLIC_API_URL" "$PUBLIC_CODE"

printf '\n[Recent NorthBound startup wrapper log]\n'
if [ -f "$NB_EMS_GATEWAY_START_LOG" ]; then
    tail -n 25 "$NB_EMS_GATEWAY_START_LOG"
else
    printf 'No startup wrapper log found at %s\n' "$NB_EMS_GATEWAY_START_LOG"
fi

printf '\n[Useful live log commands]\n'
printf 'journalctl -u nb-ems-gateway.service -f\n'
printf 'journalctl -u nb-ems-gateway.service -n 100 --no-pager\n'
printf 'cat %s\n' "$NB_EMS_GATEWAY_START_LOG"
printf '======================================\n'
printf '\n'
