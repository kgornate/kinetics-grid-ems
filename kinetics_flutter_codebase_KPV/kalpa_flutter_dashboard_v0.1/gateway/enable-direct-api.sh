#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then echo "Run on the DEBIX gateway as root."; exit 1; fi
UVICORN=/opt/ornate-ems-gateway/venv/bin/uvicorn
test -x "$UVICORN" || { echo "Kalpa backend executable not found"; exit 1; }
DIR=/etc/systemd/system/ornate-ems-gateway.service.d
DROPIN="$DIR/90-kalpa-direct-api.conf"
mkdir -p "$DIR"
if [ -f "$DROPIN" ]; then cp -a "$DROPIN" "$DROPIN.before-$(date +%Y%m%d-%H%M%S)"; fi
cat > "$DROPIN" <<'UNIT'
[Service]
ExecStart=
ExecStart=/opt/ornate-ems-gateway/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
UNIT
systemctl daemon-reload
systemctl restart ornate-ems-gateway.service
python3 - <<'CHECK'
import socket,time
for attempt in range(30):
    try:
        with socket.create_connection(("192.168.10.2",8000),timeout=1): pass
        print("PASS: Gateway API accepts TCP connections on eth0 192.168.10.2:8000")
        print("Open the Flutter app directly; SSH can be closed. Application login is still required.")
        break
    except OSError:
        time.sleep(1)
else:
    raise SystemExit("API is not reachable on eth0. Check journalctl -u ornate-ems-gateway -n 50 --no-pager")
CHECK
printf '%s\n' 'Rollback: remove /etc/systemd/system/ornate-ems-gateway.service.d/90-kalpa-direct-api.conf, then systemctl daemon-reload && systemctl restart ornate-ems-gateway'
