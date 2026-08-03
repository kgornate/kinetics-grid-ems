#!/usr/bin/env python3

import json
import os
import subprocess
import time
from datetime import datetime, timedelta

STATE_FILE = (
    "/var/lib/bess-all-pairs-scheduler/state.json"
)

SCHEDULER_SERVICE = (
    "bess-all-pairs-scheduler.service"
)

DURATION_MINUTES = 90


def log(message):
    print(
        f"[{datetime.now().isoformat(timespec='seconds')}] "
        f"{message}",
        flush=True,
    )


def scheduler_active():
    result = subprocess.run(
        [
            "systemctl",
            "is-active",
            "--quiet",
            SCHEDULER_SERVICE,
        ],
        check=False,
    )

    return result.returncode == 0


def load_state():
    with open(STATE_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_state(state):
    temporary = STATE_FILE + ".override.tmp"

    with open(
        temporary,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            state,
            file,
            indent=4,
            sort_keys=True,
        )
        file.write("\n")

    os.chmod(temporary, 0o600)
    os.replace(temporary, STATE_FILE)


log(
    "90-minute discharge-stop override started. "
    "Waiting for actual discharge start."
)

while True:
    if not scheduler_active():
        log(
            "Main scheduler is not active. "
            "Override exiting without action."
        )
        raise SystemExit(0)

    try:
        state = load_state()
    except (FileNotFoundError, json.JSONDecodeError) as error:
        log(f"Waiting for valid state file: {error}")
        time.sleep(5)
        continue

    if state.get("completed"):
        log(
            "Main schedule is already completed. "
            "Override exiting."
        )
        raise SystemExit(0)

    actual_start_text = state.get(
        "actual_discharge_start"
    )

    if not actual_start_text:
        log(
            "Discharge has not started yet; "
            "checking again in 5 seconds."
        )
        time.sleep(5)
        continue

    actual_start = datetime.fromisoformat(
        actual_start_text
    )

    stop_at = actual_start + timedelta(
        minutes=DURATION_MINUTES
    )

    # Persist the shortened stop time. This is also
    # useful if the main scheduler process later restarts.
    state["stop_at"] = stop_at.isoformat()
    state["duration_override_minutes"] = (
        DURATION_MINUTES
    )
    state["stop_override_source"] = (
        "bess-stop-after-90m.service"
    )

    save_state(state)

    log(
        f"Actual discharge started at "
        f"{actual_start.isoformat()}"
    )

    log(
        f"All-pair safe-stop scheduled for "
        f"{stop_at.isoformat()}"
    )

    while True:
        if not scheduler_active():
            log(
                "Main scheduler stopped before the "
                "90-minute target. Override exiting."
            )
            raise SystemExit(0)

        now = datetime.now(stop_at.tzinfo)
        remaining = (
            stop_at - now
        ).total_seconds()

        if remaining <= 0:
            break

        if int(remaining) % 300 < 10:
            log(
                f"Approximately "
                f"{remaining / 60:.1f} minutes remaining"
            )

        time.sleep(min(10, remaining))

    log(
        "90-minute discharge duration reached. "
        "Stopping the main scheduler safely."
    )

    # The main scheduler receives SIGTERM through
    # systemd and runs its final all-pair safe-stop:
    # zero power -> PCS stop -> BAU contactors open.
    result = subprocess.run(
        [
            "systemctl",
            "stop",
            SCHEDULER_SERVICE,
        ],
        check=False,
    )

    log(
        f"Main scheduler stop command completed "
        f"with return code {result.returncode}."
    )

    raise SystemExit(result.returncode)
