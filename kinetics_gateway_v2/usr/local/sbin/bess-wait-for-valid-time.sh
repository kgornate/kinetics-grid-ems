#!/bin/sh

MAX_WAIT_SECONDS=1800
CHECK_INTERVAL_SECONDS=15
MAX_ALLOWED_DRIFT_SECONDS=300

elapsed=0

echo "TIME-GUARD: waiting for active NTP and valid external time"

while [ "$elapsed" -lt "$MAX_WAIT_SECONDS" ]; do
    ntp_active="$(systemctl is-active ntpd.service 2>/dev/null || true)"
    sync_flag="$(timedatectl show -p NTPSynchronized --value 2>/dev/null || echo unknown)"

    remote_date=""

    for url in \
        "https://www.google.com/generate_204?ts=$(date +%s)" \
        "https://www.cloudflare.com/?ts=$(date +%s)"
    do
        remote_date="$(
            curl -sSI \
                --max-time 10 \
                -H 'Cache-Control: no-cache' \
                "$url" 2>/dev/null |
            tr -d '\r' |
            awk 'tolower($1)=="date:" {
                $1=""
                sub(/^ /,"")
                print
                exit
            }'
        )"

        [ -n "$remote_date" ] && break
    done

    if [ -n "$remote_date" ]; then
        remote_epoch="$(
            python3 - "$remote_date" <<'PY'
import email.utils
import sys

value = sys.argv[1].strip()
dt = email.utils.parsedate_to_datetime(value)

if dt.tzinfo is None:
    raise SystemExit(1)

print(int(dt.timestamp()))
PY
        )"

        case "$remote_epoch" in
            ''|*[!0-9]*)
                echo "TIME-GUARD: unable to parse external timestamp"
                ;;
            *)
                local_epoch="$(date +%s)"
                drift=$((local_epoch - remote_epoch))

                if [ "$drift" -lt 0 ]; then
                    drift=$((-drift))
                fi

                echo "TIME-GUARD: ntpd=${ntp_active} timedatectl=${sync_flag} external drift=${drift}s"

                if [ "$ntp_active" = "active" ] &&
                   [ "$drift" -le "$MAX_ALLOWED_DRIFT_SECONDS" ]; then
                    echo "TIME-GUARD: system time validation passed"
                    exit 0
                fi

                if [ "$ntp_active" != "active" ]; then
                    echo "TIME-GUARD: ntpd service is not active"
                else
                    echo "TIME-GUARD: clock drift exceeds ${MAX_ALLOWED_DRIFT_SECONDS}s"
                fi
                ;;
        esac
    else
        echo "TIME-GUARD: external timestamp unavailable"
    fi

    sleep "$CHECK_INTERVAL_SECONDS"
    elapsed=$((elapsed + CHECK_INTERVAL_SECONDS))
done

echo "TIME-GUARD ERROR: valid time was not established within ${MAX_WAIT_SECONDS}s"
exit 1
