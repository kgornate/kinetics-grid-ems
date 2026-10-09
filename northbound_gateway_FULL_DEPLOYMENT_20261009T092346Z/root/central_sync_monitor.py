#!/usr/bin/env python3

import json
import sqlite3
import subprocess
import time
import shutil

DB = "/mnt/ems-logs/northbound_ems_gateway/central_sync_outbox.db"
REFRESH = 5

STREAMS = [
    ("fast_bess_telemetry",     "S1  FAST BESS TELEMETRY"),
    ("general_asset_telemetry", "S2  GENERAL ASSET TELEMETRY"),
    ("gateway_health",          "S3  GATEWAY HEALTH"),
    ("alarms_events",           "S4  ALARMS / EVENTS"),
    ("soc_controller",          "S5  SOC CONTROLLER"),
    ("solis",                   "S6  SOLIS"),
    ("edge_ai",                 "S7  EDGE AI"),
    ("configuration_audit",     "S8  CONFIGURATION AUDIT"),
    ("command_results",         "S9  COMMAND RESULTS"),
]

RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
DIM = "\033[2m"

def clear():
    print("\033[2J\033[H", end="")

def width():
    return max(100, shutil.get_terminal_size((140, 40)).columns)

def hr(ch="="):
    print(DIM + ch * width() + RESET)

def service_state():
    try:
        return subprocess.check_output(
            ["systemctl", "is-active", "central-sync.service"],
            text=True,
            stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"

def count_state(conn, state):
    return conn.execute(
        "SELECT COUNT(*) FROM outbox_messages WHERE state=?",
        (state,)
    ).fetchone()[0]

def latest_transport(conn):
    return conn.execute("""
        SELECT
            attempted_utc,
            message_count,
            payload_bytes,
            http_status,
            outcome
        FROM transport_attempts
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()

def latest_stream(conn, stream):
    return conn.execute("""
        SELECT
            sequence,
            state,
            payload_json
        FROM outbox_messages
        WHERE stream=?
        ORDER BY created_epoch DESC
        LIMIT 1
    """, (stream,)).fetchone()

def pretty(payload):
    try:
        return json.dumps(
            json.loads(payload),
            indent=2,
            ensure_ascii=False
        )
    except Exception:
        return str(payload)

while True:
    try:
        conn = sqlite3.connect(
            f"file:{DB}?mode=ro",
            uri=True,
            timeout=3
        )
        conn.row_factory = sqlite3.Row

        clear()

        state = service_state()
        state_color = GREEN if state == "active" else RED

        print(
            BOLD + CYAN +
            " ORNATE EMS - CENTRAL SYNC LIVE MONITOR ".center(width()) +
            RESET
        )

        hr()

        pending = count_state(conn, "pending")
        retry   = count_state(conn, "retry")
        acked   = count_state(conn, "acked")
        dead    = count_state(conn, "dead")

        print(
            f"{BOLD}SERVICE:{RESET} {state_color}{state}{RESET}     "
            f"{CYAN}PENDING:{RESET} {pending}     "
            f"{YELLOW}RETRY:{RESET} {retry}     "
            f"{GREEN}ACKED:{RESET} {acked}     "
            f"{RED}DEAD:{RESET} {dead}"
        )

        tx = latest_transport(conn)

        if tx:
            tx_color = GREEN if tx["outcome"] == "http_success" else RED

            print()
            print(
                f"{BOLD}LAST BACKEND TX:{RESET} "
                f"{tx['attempted_utc']}   "
                f"msgs={tx['message_count']}   "
                f"payload={tx['payload_bytes']/1024:.1f} KB   "
                f"HTTP={tx['http_status']}   "
                f"{tx_color}{tx['outcome']}{RESET}"
            )

        hr("=")

        shown = 0

        for stream, label in STREAMS:

            row = latest_stream(conn, stream)

            if not row:
                continue

            shown += 1

            status_color = {
                "pending": CYAN,
                "acked": GREEN,
                "retry": YELLOW,
                "dead": RED,
            }.get(row["state"], RESET)

            print()
            print(
                BOLD + MAGENTA +
                f" {label} ".center(width(), "-") +
                RESET
            )

            print(
                f"{BOLD}stream:{RESET} {stream}     "
                f"{BOLD}sequence:{RESET} {row['sequence']}     "
                f"{BOLD}state:{RESET} "
                f"{status_color}{row['state']}{RESET}"
            )

            print()
            print(BOLD + "PAYLOAD:" + RESET)
            print()

            print(pretty(row["payload_json"]))

            print()
            hr("-")

        if shown == 0:
            print()
            print(
                YELLOW +
                "No current stream rows found in outbox. "
                "Waiting for next producer cycle..." +
                RESET
            )

        conn.close()

        print()
        print(
            DIM +
            f"Auto refresh: {REFRESH}s | Ctrl+C exits monitor only "
            "| Central Sync service keeps running" +
            RESET
        )

        time.sleep(REFRESH)

    except KeyboardInterrupt:
        print("\nMonitor closed.")
        break

    except Exception as e:
        print()
        print(RED + f"MONITOR ERROR: {e}" + RESET)
        print("Retrying...")
        time.sleep(3)
