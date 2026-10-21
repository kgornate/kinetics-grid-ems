#!/bin/sh
# Fresh or existing commissioning helper on the known DEBIX base profile.
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run as root'; exit 1; }
for tool in python3 wpa_cli iw ip systemctl install; do
    command -v "$tool" >/dev/null || { echo "Missing prerequisite: $tool"; exit 1; }
done
python3 -c 'import sys; assert sys.version_info >= (3,10), "Python 3.10+ required"'
[ -f /etc/wpa_supplicant/mlan0.conf ] || { echo 'Missing base profile: /etc/wpa_supplicant/mlan0.conf'; exit 1; }
for service in debix-wifi.service debix-wifi-dhcp.service; do
    systemctl cat "$service" >/dev/null || { echo "Missing base service: $service"; exit 1; }
done
ip link show eth0 >/dev/null
ip link show mlan0 >/dev/null
[ ! -f /var/lib/kalpa-setup/pending-backup ] || { echo 'A Wi-Fi change is pending. Wait for confirmation or rollback.'; exit 1; }
python3 -m py_compile "$(dirname "$0")/agent.py" "$(dirname "$0")/connectivity.py"
backup="/opt/kalpa-setup-backup-$(date +%Y%m%d-%H%M%S)"
install -d -m 700 "$backup"
if [ -f /opt/kalpa-setup/agent.py ]; then cp /opt/kalpa-setup/agent.py "$backup/"; fi
if [ -f /opt/kalpa-setup/connectivity.py ]; then cp /opt/kalpa-setup/connectivity.py "$backup/"; fi
if [ -f /etc/systemd/system/kalpa-setup.service ]; then cp /etc/systemd/system/kalpa-setup.service "$backup/"; fi
systemctl stop kalpa-setup.service 2>/dev/null || true
install -d -m 755 /opt/kalpa-setup
install -d -m 700 /var/lib/kalpa-setup
if [ ! -f /var/lib/kalpa-setup/token ]; then
python3 - <<'PY'
import os, secrets
fd = os.open('/var/lib/kalpa-setup/token', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as f: f.write(secrets.token_urlsafe(32) + '\n')
PY
fi
install -m 644 "$(dirname "$0")/agent.py" /opt/kalpa-setup/agent.py
install -m 644 "$(dirname "$0")/connectivity.py" /opt/kalpa-setup/connectivity.py
install -m 644 "$(dirname "$0")/kalpa-setup.service" /etc/systemd/system/kalpa-setup.service
systemctl daemon-reload
systemctl enable --now kalpa-setup.service
systemctl is-active --quiet kalpa-setup.service
printf '\nSetup helper installed. Current Wi-Fi configuration retained.\nBackup: %s\n' "$backup"
printf 'Setup token (private; enter in desktop app):\n'
cat /var/lib/kalpa-setup/token
