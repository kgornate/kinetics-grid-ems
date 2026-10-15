# Kalpa gateway on fresh FRDM-i.MX93 (Wi-Fi/Cloudflare already configured)

This consolidated source is based on the **user-uploaded v0.12 + Local HMI** source tree. It does **not** include the separate v0.13 protocol-level simulator. The FRDM can start with the built-in mock model and read-only HMI while the actual assets are unavailable.

## Prerequisites / safety

- Linux image must have `python3`, `venv`, `ensurepip/pip` (or equivalent), compiler/wheel support for dependencies, and outbound package access. A Yocto image may need a rebuilt root filesystem rather than `apt`.
- Preserve existing `cloudflared`, SSH, Wi-Fi, ethernet, and `weston` units.
- The installer **does not start any service or modify networking**, and installs only to `/opt/ornate-ems-gateway` and `/etc/ornate-ems-gateway`.
- Default gateway HTTP binding is `127.0.0.1:8000` for SSH-forwarded preview; it is not exposed to all interfaces.
- Central Sync is **disabled** until the real/staging backend URL and credentials have been provisioned.
- BMS/PCS write gates and the PairController are **disabled** in installed DEV mock config.
- Use the attached full source package, not the earlier historical network-install scripts.

## Windows PowerShell

```powershell
cd "$env:USERPROFILE\Downloads"
scp .\Kalpa_FRDM_Deployment_Ready_v0_12_HMI.zip gw2-ssh.unityess:/tmp/
ssh gw2-ssh.unityess
```

## On the board - preflight

```sh
uname -m
python3 --version
python3 -m venv --help
python3 -m pip --version
command -v unzip
command -v sshd
systemctl is-active cloudflared || true
systemctl is-active weston || true
free -h
df -h /
```

## Install if preflight passes

```sh
mkdir -p /tmp/kalpa_upload
unzip /tmp/Kalpa_FRDM_Deployment_Ready_v0_12_HMI.zip -d /tmp/kalpa_upload
cd /tmp/kalpa_upload/Kalpa_FRDM_Deployment_Ready_v0_12_HMI
sh deployment/kalpa_frdm_first_install.sh
```

If unzip is unavailable, use `python3 -m zipfile -e /tmp/Kalpa_FRDM_Deployment_Ready_v0_12_HMI.zip /tmp/kalpa_upload`.

## Start and test the gateway

```sh
cat /etc/ornate-ems-gateway/config.json | head -n 20
systemctl start ornate-ems-gateway.service
systemctl status ornate-ems-gateway.service --no-pager
journalctl -u ornate-ems-gateway.service -n 60 --no-pager
curl -s -o /dev/null -w 'HMI: %{http_code}\n' http://127.0.0.1:8000/hmi/
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/health
curl -s -o /dev/null -w 'HMI: %{http_code}\n' http://127.0.0.1:8000/hmi/styles.css
curl -s -o /dev/null -w 'HMI: %{http_code}\n' http://127.0.0.1:8000/hmi/app.js
```

On the Windows laptop, open a second PowerShell window and keep this tunnel active:

```powershell
ssh -N -L 18080:127.0.0.1:8000 gw2-ssh.unityess
```

Then browse `http://127.0.0.1:18080/hmi/`. To view a DEV credential locally on the trusted gateway console run:

```sh
cat /etc/ornate-ems-gateway/ornate-ems-gateway.env
```

Treat the credentials as secrets; do not paste them into chats. The dashboard can log in as customer/internal and show the four simulated Kalpa BMS+PCS pairs. The HDMI kiosk requires a Wayland-capable browser (not included in this codebase or on the previously tested Yocto image); do not assume the web page will appear on HDMI until a browser is installed.

## Central Sync when backend is ready

```sh
cd /opt/ornate-ems-gateway/backend
sh deployment/install_central_sync_v012_on_linux.sh
# central_sync.json remains enabled=false; configure backend/auth before enabling
systemctl status ornate-central-sync.service --no-pager
```

Only configure and start Central Sync after confirming the backend API, TLS, gateway identity and authentication. Do not start it while `base_url` is a placeholder.
