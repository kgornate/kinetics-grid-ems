#!/bin/sh
# Show EMS gateway status after interactive login.
case "$-" in
    *i*) ;;
    *) return 0 2>/dev/null || exit 0 ;;
esac

CONFIG_FILE="/etc/ems_network.conf"
[ -f "$CONFIG_FILE" ] && . "$CONFIG_FILE"

SHOW_NB_LOG_ON_LOGIN="${SHOW_NB_LOG_ON_LOGIN:-1}"

printf '\n'
printf '======================================\n'
printf 'EMS Gateway Network Status\n'
printf '======================================\n'

if systemctl is-active ems-network-setup.service >/dev/null 2>&1; then
    printf 'Network service : ACTIVE\n'
else
    printf 'Network service : NOT ACTIVE\n'
fi

if systemctl is-active cloudflared >/dev/null 2>&1; then
    printf 'Cloudflare      : ACTIVE\n'
else
    printf 'Cloudflare      : NOT ACTIVE\n'
fi

if systemctl is-active nb-ems-gateway.service >/dev/null 2>&1; then
    printf 'NorthBound GW   : ACTIVE\n'
else
    printf 'NorthBound GW   : NOT ACTIVE\n'
fi

printf '\n[Interface roles]\n'
printf 'eth1  : field-side Chinese EMS / external PCS\n'
printf 'eth0  : local PC/Flutter or LAN Ethernet internet\n'
printf 'mlan0 : Wi-Fi internet\n'

printf '\n[Interfaces]\n'
ip -br addr show eth0 2>/dev/null || true
ip -br addr show eth1 2>/dev/null || true
ip -br addr show mlan0 2>/dev/null || true

printf '\n[Internet route used by Cloudflare]\n'
ip route get 1.1.1.1 2>/dev/null || true

printf '\n[Field target routes]\n'
for TARGET in ${FIELD_TARGET_IPS:-192.168.1.100 192.168.1.200}; do
    ip route get "$TARGET" 2>/dev/null || true
done


printf '\n[Solis RTU]\n'
printf 'enabled=%s configured_port=%s stable_link=%s unit_id=%s baud=%s\n' "${SOLIS_RTU_ENABLED:-0}" "${SOLIS_RTU_PORT:-/dev/ttyUSB1}" "${SOLIS_RTU_STABLE_LINK:-/dev/ems_solis_rtu}" "${SOLIS_RTU_UNIT_ID:-1}" "${SOLIS_RTU_BAUDRATE:-9600}"
ls -l "${SOLIS_RTU_PORT:-/dev/ttyUSB1}" "${SOLIS_RTU_STABLE_LINK:-/dev/ems_solis_rtu}" 2>/dev/null || true
if systemctl is-active nb-ems-soc-solis-controller.service >/dev/null 2>&1; then
    printf 'SOC + Solis controller : ACTIVE\n'
else
    printf 'SOC + Solis controller : NOT ACTIVE\n'
fi

printf '\n[Local API checks]\n'
for PORT in ${LOCAL_API_PORT:-8000} ${LOCAL_LOGS_PORT:-7000}; do
    CODE="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 2 "http://127.0.0.1:$PORT/api/health" 2>/dev/null || echo 000)"
    printf '127.0.0.1:%s /api/health -> HTTP %s\n' "$PORT" "$CODE"
done

printf '\nFull network log      : cat /var/log/ems_network_setup.log\n'
printf 'NorthBound start log  : cat /var/log/nb_ems_gateway_start.log\n'
printf 'NorthBound live logs  : journalctl -u nb-ems-gateway.service -f\n'
printf 'SOC+Solis live logs   : journalctl -u nb-ems-soc-solis-controller.service -f\n'
printf '======================================\n'

# Print NorthBound details after login, similar to the network status banner.
if [ "$SHOW_NB_LOG_ON_LOGIN" = "1" ] && [ -x /root/kinetics-grid-ems/ems_network_bootup/nb_ems_gateway_status.sh ]; then
    /root/kinetics-grid-ems/ems_network_bootup/nb_ems_gateway_status.sh
fi
