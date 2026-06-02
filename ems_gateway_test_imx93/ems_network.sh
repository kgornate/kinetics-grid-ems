#!/bin/sh

# Show EMS network status after login

# Only show in interactive shell
case "$-" in
    *i*) ;;
    *) return 0 2>/dev/null || exit 0 ;;
esac

echo ""
echo "======================================"
echo "EMS Gateway Network Status"
echo "======================================"

systemctl is-active ems-network-setup.service >/dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "Service : ems-network-setup.service ACTIVE"
else
    echo "Service : ems-network-setup.service NOT ACTIVE"
fi

echo ""
echo "[Interfaces]"
ip -br addr show eth0 2>/dev/null || true
ip -br addr show eth1 2>/dev/null || true
ip -br addr show mlan0 2>/dev/null || true

echo ""
echo "[Routes]"
ip route get 192.168.10.1 2>/dev/null || true
ip route get 192.168.1.200 2>/dev/null || true
ip route get 8.8.8.8 2>/dev/null || true

echo ""
echo "Full log:"
echo "cat /var/log/ems_network_setup.log"
echo "======================================"
echo ""
EOF

chmod +x /etc/profile.d/ems_network_status.sh