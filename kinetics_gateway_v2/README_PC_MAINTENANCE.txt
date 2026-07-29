PC DEVELOPMENT AND MAINTENANCE NOTES

Main gateway application:
opt/kinetics-gateway/

Configuration:
etc/kinetics-gateway/

Cloudflare:
etc/cloudflared/

Systemd:
systemd/

Diagnostics and OOM records:
diagnostics/

Safe-stop and monitoring scripts:
operational-scripts/

Do not deploy this entire directory directly onto a live gateway.
Create controlled patches with backups, syntax validation, tests and rollback.
