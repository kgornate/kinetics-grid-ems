#!/bin/sh

set -u

BASE="http://127.0.0.1:8000"
LOG="/var/log/ems_safe_stop_all.log"

exec >>"$LOG" 2>&1

echo
echo "=================================================="
echo "$(date -Is) - ALL-PAIR SAFE STOP STARTED"
echo "=================================================="

login()
{
    rm -f /tmp/ems_safe_stop_login.json

    HTTP=$(curl -sS \
        --connect-timeout 5 \
        --max-time 60 \
        -o /tmp/ems_safe_stop_login.json \
        -w "%{http_code}" \
        -X POST \
        "$BASE/api/auth/login" \
        -H "Content-Type: application/json" \
        -d '{"username":"internal","password":"Internal@123"}')

    echo "Login HTTP=$HTTP"

    if [ "$HTTP" != "200" ]; then
        cat /tmp/ems_safe_stop_login.json 2>/dev/null
        return 1
    fi

    TOKEN=$(python3 - <<'PY'
import json

with open("/tmp/ems_safe_stop_login.json") as f:
    data = json.load(f)

print(data["access_token"])
PY
)

    [ -n "$TOKEN" ] || return 1
    export TOKEN
}

if ! login; then
    echo "$(date -Is) - ERROR: Authentication failed"
    exit 1
fi

echo "$(date -Is) - Authentication successful"

for PAIR in pair_2 pair_1 pair_3 pair_4; do
    echo
    echo "--------------------------------------------------"
    echo "$(date -Is) - SAFE-STOPPING $PAIR"
    echo "--------------------------------------------------"

    OUT="/tmp/${PAIR}_scheduled_safe_stop.json"

    HTTP=$(curl -sS \
        --connect-timeout 5 \
        --max-time 600 \
        -o "$OUT" \
        -w "%{http_code}" \
        -X POST \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d '{
          "open_bms":true,
          "confirmation":"EXECUTE_STAGE_WRITE"
        }' \
        "$BASE/api/control-sequence/${PAIR}/safe-stop")

    CURL_RC=$?

    echo "curl_rc=$CURL_RC HTTP=$HTTP"

    python3 -m json.tool "$OUT" 2>/dev/null ||
        cat "$OUT" 2>/dev/null

    sleep 10
done

echo
echo "$(date -Is) - All safe-stop commands sent"
echo "$(date -Is) - Waiting for electrical states to settle"

sleep 20

echo
echo "=================================================="
echo "$(date -Is) - FINAL PHYSICAL VERIFICATION"
echo "=================================================="

for PAIR in pair_1 pair_2 pair_3 pair_4; do
    OUT="/tmp/${PAIR}_final_safe_verification.json"

    HTTP=$(curl -sS \
        --connect-timeout 5 \
        --max-time 300 \
        -o "$OUT" \
        -w "%{http_code}" \
        -H "Authorization: Bearer $TOKEN" \
        "$BASE/api/control-sequence/${PAIR}/status?fresh=true")

    echo
    echo "$PAIR verification HTTP=$HTTP"

    PAIR="$PAIR" python3 - <<'PY'
import json
import os

pair = os.environ["PAIR"]
path = f"/tmp/{pair}_final_safe_verification.json"

try:
    with open(path) as f:
        d = json.load(f)
except Exception as error:
    print({
        "pair": pair,
        "SAFE_BASELINE": False,
        "read_error": str(error),
    })
    raise SystemExit

s = d.get("summary", {})

precharge = s.get("precharge_state")
positive = s.get("positive_contactor_closed")
negative = s.get("negative_contactor_closed")
state = s.get("pcs_operating_state")
setpoint = s.get("pcs_power_setpoint_kw")
actual = s.get("pcs_actual_power_kw")
errors = d.get("errors", [])

safe = (
    precharge == 0
    and positive is False
    and negative is False
    and state in (1, 1.0)
    and setpoint is not None
    and abs(float(setpoint)) <= 1.0
    and actual is not None
    and abs(float(actual)) <= 3.0
    and not errors
)

print({
    "pair": pair,
    "SAFE_BASELINE": safe,
    "precharge_state": precharge,
    "contactors": (positive, negative),
    "pcs_state": state,
    "setpoint_kw": setpoint,
    "actual_kw": actual,
    "pcs_input_v": s.get("pcs_battery_voltage_v"),
    "pcs_dc_bus_v": s.get("pcs_dc_bus_voltage_v"),
    "errors": errors,
})
PY
done

echo
echo "=================================================="
echo "$(date -Is) - ALL-PAIR SAFE STOP FINISHED"
echo "=================================================="
