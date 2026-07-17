# EMS V3 Deploy Bundle

This bundle packages the currently working EMS V3 boot, networking, status-banner, systemd, and gateway/SOC config files from the deployed unit.

## What this bundle installs
- `/etc/ems_boot_v3.conf`
- `/etc/nb_ems_gateway.conf`
- `/etc/cloudflared/config.yml`
- `/etc/profile.d/ems_network_status.sh`
- EMS V3 systemd units:
  - `ems-v3-eth1.service`
  - `ems-v3-wifi.service`
  - `cloudflared.service`
  - `ems-v3-solis-link.service`
  - `ems-v3-gateway.service`
  - `ems-v3-soc-controller.service`
  - `ems-v3-app-stack.target`
  - `ems-v3-soc-controller.service.d/10-after-gateway.conf`
- Boot/runtime scripts under `/root/kinetics-grid-ems/ems_boot_v3/scripts`
- Gateway wrapper and banner scripts under `/root/kinetics-grid-ems/ems_network_bootup`
- Gateway/SOC config JSON files under `/root/kinetics-grid-ems/northbound_ems_gateway/configs`

## Important scope
This bundle is the **platform + integration layer snapshot**. It does **not** include the full gateway application codebase or Python dependencies. On a new unit, you still need:
- the `kinetics-grid-ems` repo/codebase present under `/root/kinetics-grid-ems`
- Python and required dependencies installed
- Cloudflare binary available at `/usr/local/bin/cloudflared`

## Current architecture
Boot/app order is intended to be:
1. `ems-v3-eth1.service`
2. `ems-v3-wifi.service`
3. `cloudflared.service`
4. `ems-v3-solis-link.service`
5. `ems-v3-app-stack.target`
   - pulls in `ems-v3-gateway.service`
   - pulls in `ems-v3-soc-controller.service`
6. SOC controller has an override to start **after** gateway

## Install on another unit
Run as root:

```bash
./install.sh
./post_install_check.sh
reboot
```

## Upgrade on an existing unit
```bash
./upgrade.sh
./post_install_check.sh
```

## Backups
`install.sh` saves overwritten files under:

```text
/root/ems_v3_install_backups/<timestamp>/
```

## Notes / current values captured from the source unit
This bundle contains deployed configuration values from the source unit, including:
- field IPs (`192.168.100.151`, `192.168.100.153`)
- Wi-Fi SSID/password from `/etc/ems_boot_v3.conf`
- Cloudflare config from `/etc/cloudflared/config.yml`
- gateway config path `configs/development.json`
- gateway real mode (`NB_EMS_GATEWAY_MOCK="0"`)

Review these values before using on a different site or customer unit.
