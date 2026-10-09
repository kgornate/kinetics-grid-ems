#!/usr/bin/env python3

import json
import os
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime, timezone

DB = "/mnt/ems-logs/northbound_ems_gateway/central_sync_outbox.db"
CFG = "/root/kinetics-grid-ems/northbound_ems_gateway/configs/central_sync.json"

REFRESH_SEC = 3

# Maximum JSON characters shown for one stream.
# Increase this if you want more of large S2 payloads.
MAX_PAYLOAD_CHARS = 12000

STREAM_ORDER = [
    "fast_bess_telemetry",
    "general_asset_telemetry",
    "gateway_health",
    "alarms_events",
    "soc_controller",
    "solis",
    "edge_ai",
    "configuration_audit",
    "command_results",
]

STREAM_LABEL = {
    "fast_bess_telemetry":      "S1  FAST BESS TELEMETRY",
    "general_asset_telemetry":  "S2  GENERAL ASSET TELEMETRY",
    "gateway_health":           "S3  GATEWAY HEALTH",
    "alarms_events":            "S4  ALARMS / EVENTS",
    "soc_controller":           "S5  SOC CONTROLLER",
    "solis":                    "S6  SOLIS",
    "edge_ai":                  "S7  EDGE AI",
    "configuration_audit":      "S8  CONFIGURATION AUDIT",
    "command_results":          "S9  COMMAND RESULTS",
}

# ANSI
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
WHITE = "\033[97m"

BG_BLUE = "\033[44m"
BG_GREEN = "\033[42m"

def clear():
    print("\033[2J\033[H", end="")

def term_width():
    return max(100, min(shutil.get_terminal_size((140, 40)).columns, 180))

def line(char="─"):
    print(DIM + char * term_width() + RESET)

def service_state():
    try:
        return subprocess.check_output(
            ["systemctl", "is-active", "central-sync.service"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"

def cfg_info():
    try:
        with open(CFG) as f:
            c = json.load(f)
        return {
            "version": c.get("identity", {}).get("software_version", "?"),
            "gateway": c.get("identity", {}).get("gateway_id", "?"),
            "site": c.get("identity", {}).get("site_id", "?"),
            "source_ip": c.get("backend", {}).get("source_ip"),
        }
    except Exception:
        return {}

def pretty_json(text):
    try:
        obj = json.loads(text)
        out = json.dumps(
            obj,
            indent=2,
            ensure_ascii=False,
            sort_keys=False,
        )
    except Exception:
        out = str(text)

    if len(out) > MAX_PAYLOAD_CHARS:
        remaining = len(out) - MAX_PAYLOAD_CHARS
        out = (
            out[:MAX_PAYLOAD_CHARS]
            + "\n"
            + YELLOW
            + f"... payload display truncated ({remaining:,} characters hidden)"
            + RESET
        )

    return out

def one_value(conn, sql, args=()):
    r = conn.execute(sql, args).fetchone()
    if not r:
        return 0
    return r[0]

def get_stream_names(conn):
    found = {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT stream FROM outbox_messages"
        ).fetchall()
        if r[0]
    }

    ordered = [s for s in STREAM_ORDER if s in found]
    ordered.extend(sorted(found - set(ordered)))
    return ordered

def latest_payload(conn, stream):
    return conn.execute(
        """
        SELECT
            message_id,
            sequence,
            state,
            created_epoch,
            payload_json,
            payload_bytes
        FROM outbox_messages
        WHERE stream = ?
        ORDER BY created_epoch DESC, message_id DESC
        LIMIT 1
        """,
        (stream,),
    ).fetchone()

def main():
    while True:
        try:
            conn = sqlite3.connect(
                f"file:{DB}?mode=ro",
                uri=True,
                timeout=2,
            )
            conn.row_factory = sqlite3.Row

            clear()

            width = term_width()
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

            print(
                BG_BLUE
                + WHITE
                + BOLD
                + " ORNATE EMS — CENTRAL SYNC LIVE MONITOR ".center(width)
                + RESET
            )

            info = cfg_info()
            state = service_state()

            state_color = GREEN if state == "active" else RED

            print()
            print(
                f"{BOLD}Time:{RESET} {now}    "
                f"{BOLD}Service:{RESET} {state_color}{state}{RESET}    "
                f"{BOLD}Version:{RESET} {CYAN}{info.get('version','?')}{RESET}"
            )

            print(
                f"{BOLD}Gateway:{RESET} {info.get('gateway','?')}    "
                f"{BOLD}Site:{RESET} {info.get('site','?')}    "
                f"{BOLD}Source IP:{RESET} {info.get('source_ip')}"
            )

            line()

            pending = one_value(
                conn,
                'SELECT COUNT(*) FROM outbox_messages WHERE state="pending"'
            )
            retry = one_value(
                conn,
                'SELECT COUNT(*) FROM outbox_messages WHERE state="retry"'
            )
            acked = one_value(
                conn,
                'SELECT COUNT(*) FROM outbox_messages WHERE state="acked"'
            )
            dead = one_value(
                conn,
                'SELECT COUNT(*) FROM outbox_messages WHERE state="dead"'
            )

            ok30 = one_value(
                conn,
                """
                SELECT COUNT(*)
                FROM transport_attempts
                WHERE attempted_utc >=
                      strftime('%Y-%m-%dT%H:%M:%S','now','-30 seconds')
                  AND outcome='http_success'
                """
            )

            fail30 = one_value(
                conn,
                """
                SELECT COUNT(*)
                FROM transport_attempts
                WHERE attempted_utc >=
                      strftime('%Y-%m-%dT%H:%M:%S','now','-30 seconds')
                  AND outcome!='http_success'
                """
            )

            last_tx = conn.execute(
                """
                SELECT
                    attempted_utc,
                    message_count,
                    payload_bytes,
                    http_status,
                    outcome
                FROM transport_attempts
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

            retry_color = GREEN if retry == 0 else YELLOW
            dead_color = GREEN if dead == 0 else RED
            fail_color = GREEN if fail30 == 0 else RED

            print(
                BG_GREEN
                + WHITE
                + BOLD
                + " CENTRAL SYNC / OUTBOX ".ljust(width)
                + RESET
            )

            print()
            print(
                f"  {CYAN}PENDING{RESET}  {pending:<8}"
                f"  {retry_color}RETRY{RESET}  {retry:<8}"
                f"  {GREEN}ACKED{RESET}  {acked:<8}"
                f"  {dead_color}DEAD{RESET}  {dead:<8}"
                f"  {GREEN}HTTP OK/30s{RESET}  {ok30:<6}"
                f"  {fail_color}FAIL/30s{RESET}  {fail30:<6}"
            )

            if last_tx:
                txcolor = (
                    GREEN
                    if last_tx["outcome"] == "http_success"
                    else RED
                )

                print()
                print(
                    "  Last TX : "
                    f"{last_tx['attempted_utc']}   "
                    f"msgs={last_tx['message_count']}   "
                    f"payload={last_tx['payload_bytes']/1024:.1f} KB   "
                    f"HTTP={last_tx['http_status']}   "
                    f"{txcolor}{last_tx['outcome']}{RESET}"
                )

            page_size = one_value(conn, "PRAGMA page_size")
            page_count = one_value(conn, "PRAGMA page_count")
            freelist = one_value(conn, "PRAGMA freelist_count")

            physical_mb = page_size * page_count / 1024 / 1024
            live_mb = page_size * (page_count - freelist) / 1024 / 1024
            free_mb = page_size * freelist / 1024 / 1024

            print(
                f"  SQLite  : physical={physical_mb:.1f} MB   "
                f"live={live_mb:.1f} MB   "
                f"reusable={free_mb:.1f} MB"
            )

            line("═")

            streams = get_stream_names(conn)

            if not streams:
                print(RED + "No stream messages found in outbox." + RESET)

            for stream in streams:
                row = latest_payload(conn, stream)

                if not row:
                    continue

                label = STREAM_LABEL.get(stream, stream.upper())

                state = row["state"]
                scolor = (
                    GREEN if state == "acked"
                    else CYAN if state == "pending"
                    else YELLOW if state == "retry"
                    else RED
                )

                print()
                print(
                    MAGENTA
                    + BOLD
                    + f"┌─ {label} "
                    + "─" * max(1, width - len(label) - 6)
                    + RESET
                )

                print(
                    f"{BOLD}│ stream:{RESET} {stream}    "
                    f"{BOLD}seq:{RESET} {row['sequence']}    "
                    f"{BOLD}state:{RESET} {scolor}{state}{RESET}"
                )

                print(
                    f"{BOLD}│ created:{RESET} {row['created_utc']}    "
                    f"{BOLD}payload:{RESET} {row['payload_bytes']/1024:.1f} KB    "
                    f"{BOLD}message_id:{RESET} {row['message_id']}"
                )

                print(
                    MAGENTA
                    + "├─ ACTUAL CENTRAL SYNC PAYLOAD"
                    + RESET
                )

                payload = pretty_json(row["payload_json"])

                for ln in payload.splitlines():
                    print("│ " + ln)

                print(MAGENTA + "└" + "─" * (width - 1) + RESET)

            conn.close()

            print()
            line()
            print(
                DIM
                + f"Refresh every {REFRESH_SEC}s | Ctrl+C to exit | "
                  f"payload display limit={MAX_PAYLOAD_CHARS:,} chars/stream"
                + RESET
            )

            time.sleep(REFRESH_SEC)

        except KeyboardInterrupt:
            print("\nMonitor stopped.")
            break

        except Exception as exc:
            clear()
            print(RED + BOLD + "MONITOR ERROR" + RESET)
            print(repr(exc))
            print()
            print("Retrying in 3 seconds...")
            time.sleep(3)

if __name__ == "__main__":
    main()
