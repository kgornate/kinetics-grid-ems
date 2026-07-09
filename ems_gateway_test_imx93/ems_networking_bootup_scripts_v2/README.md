# EMS Networking Bootup Scripts v2 - NorthBound + Cloudflare + Auto Gateway Start

This package configures the FRDM-i.MX93 network interfaces at Linux boot and then starts the **NorthBound EMS Gateway** automatically after the network setup has completed.

The intended field boot sequence is:

```text
i.MX93 power ON
  -> Linux boots
  -> ems-network-setup.service runs first
  -> eth1/eth0/mlan0 routes are configured
  -> cloudflared can use the active internet route
  -> nb-ems-gateway.service starts after network setup
  -> NorthBound Gateway runs local API on port 8000
  -> Cloudflare exposes it as https://ems-api.unityess.cloud
```

## Interface model

- `eth1` = field-side network for Chinese EMS or external PCS.
- `eth0` = application-side network: either direct PC/Flutter or LAN Ethernet internet.
- `mlan0` = Wi-Fi internet, continuing like the current working setup.

Remote monitoring uses Cloudflare Tunnel. Cloudflare only needs the i.MX93 to have internet. It can use internet from `mlan0` Wi-Fi or from `eth0` LAN, depending on the Linux default route.

## Important files

| File | Purpose |
| --- | --- |
| `config/ems_network.conf` | Main editable network configuration. Installed to `/etc/ems_network.conf`. |
| `config/nb_ems_gateway.conf` | NorthBound Gateway startup configuration. Installed to `/etc/nb_ems_gateway.conf`. |
| `scripts/ems_network_all_setup.sh` | Main boot-time network setup script. |
| `scripts/nb_ems_gateway_start.sh` | Startup wrapper for NorthBound Gateway with boot diagnostics/logs. |
| `systemd/ems-network-setup.service` | First boot service: configures eth1/eth0/Wi-Fi routes. |
| `systemd/nb-ems-gateway.service` | Second boot service: starts NorthBound Gateway after network setup. |
| `install_network_bootup.sh` | Installer for i.MX93. |

## Service ordering

`nb-ems-gateway.service` has:

```ini
Requires=ems-network-setup.service
After=ems-network-setup.service network-online.target
```

This means the NorthBound Gateway service starts **after** the network setup service.

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

## NorthBound Gateway default startup mode

By default the installed `/etc/nb_ems_gateway.conf` starts the gateway in mock/testing mode:

```text
NB_EMS_GATEWAY_CONFIG="configs/development.json"
NB_EMS_GATEWAY_MOCK="1"
```

For actual field mode later, edit `/etc/nb_ems_gateway.conf`:

```text
NB_EMS_GATEWAY_CONFIG="configs/actual_site.json"
NB_EMS_GATEWAY_MOCK="0"
```

Then restart:

```bash
systemctl restart nb-ems-gateway.service
```

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

and configs to:

```text
/etc/ems_network.conf
/etc/nb_ems_gateway.conf
```

It enables and starts:

```text
ems-network-setup.service
nb-ems-gateway.service
```

## Useful commands

```bash
cat /etc/ems_network.conf
cat /etc/nb_ems_gateway.conf
cat /var/log/ems_network_setup.log
cat /var/log/nb_ems_gateway_start.log

systemctl status ems-network-setup.service --no-pager
systemctl status nb-ems-gateway.service --no-pager
journalctl -u ems-network-setup.service -n 100 --no-pager
journalctl -u nb-ems-gateway.service -n 100 --no-pager
journalctl -u nb-ems-gateway.service -f

/root/kinetics-grid-ems/ems_network_bootup/route_check.sh
ip route get 1.1.1.1
curl http://127.0.0.1:8000/api/health
curl https://ems-api.unityess.cloud/api/health
```

## Logs after boot

The services use:

```ini
StandardOutput=journal+console
StandardError=journal+console
```

So boot-time logs go to both systemd journal and the system console. Wrapper-level NorthBound startup checks are also written to:

```text
/var/log/nb_ems_gateway_start.log
```

Network setup logs are written to:

```text
/var/log/ems_network_setup.log
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

## Undo / disable auto start

```bash
systemctl stop nb-ems-gateway.service
systemctl disable nb-ems-gateway.service
rm -f /etc/systemd/system/nb-ems-gateway.service
systemctl daemon-reload
systemctl reset-failed nb-ems-gateway.service
```

## Login terminal output behavior

The boot services run in the background, but this package installs:

```text
/etc/profile.d/ems_network_status.sh
```

This profile script runs automatically whenever an interactive SSH/serial shell is opened. It prints:

- network service status
- Cloudflare status
- NorthBound gateway service status
- interface and route information
- local API health
- public Cloudflare API health
- recent NorthBound startup log lines

This is why status/log information appears in the terminal after boot/login. For continuous live gateway logs, run:

```bash
journalctl -u nb-ems-gateway.service -f
```

To disable the NorthBound log section on login, edit `/etc/nb_ems_gateway.conf`:

```bash
SHOW_NB_LOG_ON_LOGIN="0"
```


PYTHONPATH=src python3 -m nb_ems_gateway.main --config configs/development.json --mock

Yes, exactly.

After the NorthBound Gateway is running as a systemd service, you can run:

journalctl -u nb-ems-gateway.service -f

and you will see the continuous live logs from the gateway, similar to what you see when you manually run:

PYTHONPATH=src python3 -m nb_ems_gateway.main --config configs/development.json --mock

The difference is only where the process is running.

When you run manually, the Python process is attached directly to your terminal, so logs print there.

When systemd runs it automatically after boot, the Python process runs in the background, so logs go into systemd journal. journalctl -u nb-ems-gateway.service -f attaches your terminal to that journal stream.

So after boot, do this:

systemctl status nb-ems-gateway.service --no-pager
journalctl -u nb-ems-gateway.service -f

You should see lines like:

NorthBound EMS Gateway
  mode: read_only
  mock: True
  EMS: 127.0.0.1:515, unit=1
  register points: 1421
  API: http://0.0.0.0:8000
Polling scheduler started for groups: ['default', 'fast', 'slow']
Uvicorn running on http://0.0.0.0:8000

To stop watching logs, press:

CTRL + C

This will only stop the log viewing command. It will not stop the gateway service.

To stop the actual gateway service, that would be:

systemctl stop nb-ems-gateway.service
## v2.1 Wi-Fi robustness update

This package includes an updated `scripts/imx93_wifi_setup.sh` based on the field debug flow that successfully reconnects primary Wi-Fi.

Changes:
- waits for `mlan0` to exist before Wi-Fi setup
- cleanly restarts `wpa_supplicant` and `udhcpc`
- waits for `wpa_state=COMPLETED`
- triggers reassociation during slow AP scans
- retries DHCP before failing
- keeps optional static fallback disabled by default
- keeps EMS field network on `eth1 = 192.168.100.2/24`
- checks Chinese EMS targets `192.168.100.151` and `192.168.100.153`

Default Wi-Fi retry tuning is in `config/ems_network.conf`:

```sh
WIFI_IFACE_WAIT_ATTEMPTS="30"
WIFI_CONNECT_ATTEMPTS="12"
WIFI_CONNECT_SLEEP_SEC="2"
WIFI_DHCP_ATTEMPTS="3"
WIFI_DHCP_TRIES_PER_ATTEMPT="5"
WIFI_DHCP_TIMEOUT_SEC="2"
WIFI_STATIC_FALLBACK_ENABLED="0"
```

After install, validate with:

```sh
/root/kinetics-grid-ems/ems_network_bootup/imx93_wifi_setup.sh
wpa_cli -p /var/run/wpa_supplicant -i mlan0 status
ip -br addr show mlan0
ip route
ping -I mlan0 -c 3 8.8.8.8
```

---

# v2.2 Solis Modbus RTU boot setup addition

This package also prepares the Solis inverter RS485/Modbus RTU port during boot.

Boot sequence becomes:

```text
i.MX93 power ON
  -> Linux boots
  -> ems-network-setup.service runs
  -> eth1/eth0/mlan0 are configured
  -> Solis USB-RS485 serial port is detected
  -> /dev/ems_solis_rtu stable symlink is created
  -> serial mode is set to 9600 8N1 raw mode
  -> configs/soc_solis_field_rtu.json is patched to use /dev/ems_solis_rtu
  -> optional read-only Solis Modbus RTU probe runs
  -> application/controller can start after setup
```

## Solis RTU config

Edit `/etc/ems_network.conf` after installation if the USB adapter appears on a different port:

```bash
SOLIS_RTU_ENABLED="1"
SOLIS_RTU_PORT="/dev/ttyUSB1"
SOLIS_RTU_STABLE_LINK="/dev/ems_solis_rtu"
SOLIS_RTU_BAUDRATE="9600"
SOLIS_RTU_UNIT_ID="1"
SOLIS_RTU_BOOT_READ_TEST="1"
SOLIS_RTU_REQUIRED="0"
SOC_SOLIS_GATEWAY_CONFIG="/root/kinetics-grid-ems/northbound_ems_gateway/configs/soc_solis_field_rtu.json"
```

`SOLIS_RTU_REQUIRED="0"` means boot will continue even if the inverter is disconnected. Set it to `1` only after the field wiring is final and you want boot to fail if Solis RTU is not detected.

## Solis RTU manual checks

```bash
ls -l /dev/ttyUSB* /dev/ems_solis_rtu
stty -F /dev/ems_solis_rtu -a
/root/kinetics-grid-ems/ems_network_bootup/solis_rtu_modbus_check.py --port /dev/ems_solis_rtu --baudrate 9600 --unit-id 1
cat /var/log/ems_network_setup.log | grep -i solis -A30
```

## SOC + Solis controller service

The installer also copies this service file:

```text
/etc/systemd/system/nb-ems-soc-solis-controller.service
```

It is installed but not enabled automatically, so that the field team can finish manual Solis read/write validation first. After validation:

```bash
systemctl stop nb-ems-gateway.service
systemctl disable nb-ems-gateway.service
systemctl enable nb-ems-soc-solis-controller.service
systemctl start nb-ems-soc-solis-controller.service
journalctl -u nb-ems-soc-solis-controller.service -f
```

Emergency stop:

```bash
systemctl stop nb-ems-soc-solis-controller.service
```
