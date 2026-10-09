#!/usr/bin/env python3

import json
import sqlite3
import subprocess
import shutil
import time
from datetime import datetime, timezone

DB = "/mnt/ems-logs/northbound_ems_gateway/central_sync_outbox.db"
REFRESH = 3
PREVIEW = 150

STREAMS = [
    ("fast_bess_telemetry",     "S1 FAST BESS"),
    ("general_asset_telemetry", "S2 GENERAL ASSET"),
    ("gateway_health",          "S3 GATEWAY HEALTH"),
    ("alarms_events",           "S4 ALARMS/EVENTS"),
    ("soc_controller",          "S5 SOC CTRL"),
    ("solis",                   "S6 SOLIS"),
    ("edge_ai",                 "S7 EDGE AI"),
    ("configuration_audit",     "S8 CONFIG AUDIT"),
    ("command_results",         "S9 COMMAND RESULT"),
]

R  = "\033[0m"
B  = "\033[1m"
DIM= "\033[2m"
G  = "\033[32m"
Y  = "\033[33m"
RED= "\033[31m"
C  = "\033[36m"
M  = "\033[35m"
W  = "\033[97m"

def clear():
    print("\033[2J\033[H", end="")

def width():
    return min(max(shutil.get_terminal_size((150, 40)).columns, 110), 180)

def service_state():
    try:
        return subprocess.check_output(
            ["systemctl", "is-active", "central-sync.service"],
            text=True,
            stderr=subprocess.DEVNULL
        ).strip()
    except:
        return "unknown"

def count(conn, state):
    return conn.execute(
        "SELECT COUNT(*) FROM outbox_messages WHERE state=?",
        (state,)
    ).fetchone()[0]

def latest_stream(conn, stream):
    return conn.execute("""
        SELECT
            sequence,
            state,
            created_epoch,
            payload_bytes,
            payload_json
        FROM outbox_messages
        WHERE stream=?
        ORDER BY created_epoch DESC
        LIMIT 1
    """, (stream,)).fetchone()

def payload_summary(text):
    try:
        obj = json.loads(text)

        if isinstance(obj, dict):
            keys = list(obj.keys())

            parts = []

            for k, v in list(obj.items())[:5]:
                if isinstance(v, list):
                    parts.append(f"{k}[{len(v)}]")
                elif isinstance(v, dict):
                    parts.append(f"{k}{{{len(v)}}}")
                elif isinstance(v, (str, int, float, bool)) or v is None:
                    val = str(v)
                    if len(val) > 20:
                        val = val[:17] + "..."
                    parts.append(f"{k}={val}")

            shape = f"object:{len(keys)} keys"

            if parts:
                shape += " | " + ", ".join(parts)

        elif isinstance(obj, list):
            shape = f"list:{len(obj)} records"
        else:
            shape = type(obj).__name__

        preview = json.dumps(
            obj,
            separators=(",", ":"),
            ensure_ascii=False
        )

        if len(preview) > PREVIEW:
            preview = preview[:PREVIEW] + "..."

        return shape, preview

    except:
        text = str(text)
        return "raw", text[:PREVIEW]

while True:
    try:
        conn = sqlite3.connect(
            f"file:{DB}?mode=ro",
            uri=True,
            timeout=2
        )
        conn.row_factory = sqlite3.Row

        clear()

        w = width()
        now = datetime.now(timezone.utc)

        svc = service_state()
        svc_col = G if svc == "active" else RED

        p = count(conn, "pending")
        r = count(conn, "retry")
        a = count(conn, "acked")
        d = count(conn, "dead")

        ok30 = conn.execute("""
            SELECT COUNT(*)
            FROM transport_attempts
            WHERE attempted_utc >=
                  strftime('%Y-%m-%dT%H:%M:%S','now','-30 seconds')
              AND outcome='http_success'
        """).fetchone()[0]

        fail30 = conn.execute("""
            SELECT COUNT(*)
            FROM transport_attempts
            WHERE attempted_utc >=
                  strftime('%Y-%m-%dT%H:%M:%S','now','-30 seconds')
              AND outcome!='http_success'
        """).fetchone()[0]

        tx = conn.execute("""
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

        print(B + C + " ORNATE EMS | CENTRAL SYNC LIVE ".center(w, "=") + R)

        print(
            f"{B}SERVICE{R} {svc_col}{svc}{R}   "
            f"{C}PENDING{R} {p:<4} "
            f"{Y}RETRY{R} {r:<3} "
            f"{G}ACKED{R} {a:<4} "
            f"{RED}DEAD{R} {d:<3}   "
            f"{G}HTTP OK/30s{R} {ok30:<3} "
            f"{RED}FAIL/30s{R} {fail30:<3}"
        )

        if tx:
            col = G if tx["outcome"] == "http_success" else RED

            print(
                f"{B}LAST TX{R} "
                f"HTTP={tx['http_status']} "
                f"{col}{tx['outcome']}{R} | "
                f"msgs={tx['message_count']} | "
                f"{tx['payload_bytes']/1024:.1f}KB | "
                f"{tx['attempted_utc']}"
            )

        print(DIM + "-" * w + R)

        print(
            f"{B}{'STREAM':<21}"
            f"{'SEQ':>9}  "
            f"{'STATE':<8}"
            f"{'SIZE':>9}  "
            f"{'AGE':>7}   "
            f"PAYLOAD SUMMARY{R}"
        )

        print(DIM + "-" * w + R)

        for stream, label in STREAMS:

            row = latest_stream(conn, stream)

            if not row:
                print(
                    f"{DIM}{label:<21}"
                    f"{'-':>9}  "
                    f"{'NO DATA':<8}"
                    f"{'-':>9}  "
                    f"{'-':>7}{R}"
                )
                continue

            age = max(
                0,
                int(now.timestamp() - row["created_epoch"])
            )

            state = row["state"]

            state_col = {
                "pending": C,
                "acked": G,
                "retry": Y,
                "dead": RED
            }.get(state, W)

            shape, preview = payload_summary(row["payload_json"])

            print(
                f"{M}{label:<21}{R}"
                f"{row['sequence']:>9}  "
                f"{state_col}{state:<8}{R}"
                f"{row['payload_bytes']/1024:>8.1f}K  "
                f"{age:>5}s   "
                f"{shape}"
            )

            print(
                DIM +
                "   ↳ " +
                preview[:max(40, w-6)] +
                R
            )

        print(DIM + "-" * w + R)
        print(
            f"{DIM}"
            f"Refresh {REFRESH}s | Ctrl+C exits monitor only | "
            f"Service continues running"
            f"{R}"
        )

        conn.close()
        time.sleep(REFRESH)

    except KeyboardInterrupt:
        print("\nMonitor closed.")
        break

    except Exception as e:
        print(RED + f"\nMonitor error: {e}" + R)
        time.sleep(2)
