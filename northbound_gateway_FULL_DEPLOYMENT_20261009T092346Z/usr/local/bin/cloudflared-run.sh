#!/bin/sh
exec /usr/local/bin/cloudflared --no-autoupdate --config /etc/cloudflared/config.yml tunnel run >> /var/log/cloudflared_service.log 2>&1
