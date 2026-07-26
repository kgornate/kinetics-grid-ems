# EMS V3 Wi-Fi Boot Package for FRDM-i.MX93

## Networks

- Primary: `OnePlus 13s CF94`
- Backup: `BESS_Ornate 1`

## Installed files

- `/etc/ems_wifi_boot.conf`
- `/root/northbound-ems/ems_boot_v3/scripts/imx93_wifi_v3.sh`
- `/root/northbound-ems/ems_boot_v3/scripts/ems_v3_wifi_status.sh`
- `/etc/systemd/system/ems-v3-wifi.service`

## Install

Copy this directory to the board, then:

```sh
cd /tmp/ems_v3_wifi_boot
bash install_wifi_boot.sh
```

## Verify before reboot

```sh
systemctl status ems-v3-wifi.service --no-pager
/root/northbound-ems/ems_boot_v3/scripts/ems_v3_wifi_status.sh
```

## Reboot test

```sh
reboot
```

After reboot:

```sh
systemctl is-enabled ems-v3-wifi.service
systemctl is-active ems-v3-wifi.service
/root/northbound-ems/ems_boot_v3/scripts/ems_v3_wifi_status.sh
```

## Logs

```sh
journalctl -u ems-v3-wifi.service -b --no-pager
cat /var/log/ems_wifi_boot.log
```

## Important

This package disables ConnMan and the generic wpa_supplicant service so that only `ems-v3-wifi.service` owns `mlan0`.

Cloudflare is intentionally not configured by this package. When the IT team provides new tunnel credentials/config, its service should use:

```text
/usr/bin/cloudflared
```
