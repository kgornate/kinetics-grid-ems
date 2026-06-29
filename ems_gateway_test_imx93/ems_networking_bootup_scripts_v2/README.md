# EMS Networking Bootup Scripts v2 - NorthBound + Cloudflare Mode

This package replaces the earlier EMS boot networking scripts with a clearer interface model:

- `eth1` = field-side network for Chinese EMS or external PCS.
- `eth0` = application-side network: either direct PC/Flutter or LAN Ethernet internet.
- `mlan0` = Wi-Fi internet, continuing like the current working setup.

Remote monitoring is expected to use Cloudflare Tunnel. Cloudflare only needs the i.MX93 to have internet. It can use internet from `mlan0` Wi-Fi or from `eth0` LAN, depending on the Linux default route.

## Important files

- `config/ems_network.conf` - main editable network configuration.
- `scripts/ems_network_all_setup.sh` - main boot-time network setup script.
- `systemd/ems-network-setup.service` - boot-time systemd service.
- `install_network_bootup.sh` - installer for i.MX93.

## Default behavior

`ETH0_MODE="auto"`

This means:

1. Try DHCP on `eth0` first. If `eth0` is connected to a LAN/router, it can get internet.
2. If DHCP fails, fall back to static direct-PC mode: `192.168.10.2/24`.

`eth1` is static by default:

```text
eth1 = 192.168.1.2/24
```

Field target checks include:

```text
192.168.1.100  # expected future Chinese EMS placeholder
192.168.1.200  # existing PCS/default external PCS target
```

Change these in `/etc/ems_network.conf` after vendor confirms the Chinese EMS IP/subnet.

## Install on i.MX93

Copy this folder to the i.MX93, then run:

```bash
cd /tmp/ems_networking_bootup_scripts_v2
sh install_network_bootup.sh
```

The installer copies scripts to:

```text
/root/kinetics-grid-ems/ems_network_bootup
```

and config to:

```text
/etc/ems_network.conf
```

## Common commands

```bash
cat /etc/ems_network.conf
cat /var/log/ems_network_setup.log
systemctl status ems-network-setup.service --no-pager
/root/kinetics-grid-ems/ems_network_bootup/route_check.sh
ip route get 1.1.1.1
```

## Cloudflare note

Cloudflare is managed by its own service and config:

```text
/etc/cloudflared/config.yml
cloudflared.service
```

These networking scripts do not decide Cloudflare protocol. They only ensure the i.MX93 has correct local interfaces and at least one working internet route.

For best reliability, Cloudflare config should route to IPv4 localhost:

```yaml
service: http://127.0.0.1:8000
```

instead of:

```yaml
service: http://localhost:8000
```
