#!/bin/sh
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run as root'; exit 1; }
systemctl cat cloudflared.service >/dev/null || { echo 'Provision this gateway own Cloudflare tunnel first'; exit 1; }
install -d -m 755 /etc/systemd/system/cloudflared.service.d
path=/etc/systemd/system/cloudflared.service.d/20-ipv4-test.conf
if [ -f "$path" ]; then cp -p "$path" "$path.backup-$(date +%Y%m%d-%H%M%S)"; fi
cat > "$path" <<'EOF'
[Service]
Environment="TUNNEL_EDGE_IP_VERSION=4"
EOF
systemctl daemon-reload
systemctl restart cloudflared.service
printf 'IPv4 setting applied to cloudflared. Check new registered connections use IPv4.\n'
printf 'Remote sessions may briefly disconnect. Verify tunnel readiness in the desktop app.\n'
