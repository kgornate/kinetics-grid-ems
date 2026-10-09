#!/bin/sh
exec python3 - <<'PY'
import json
import os
import sqlite3
import subprocess
import time
from datetime import datetime, timezone

LIVE_STATUS = "/var/lib/nb-ems-central-sync/status.json"
REC_STATUS  = "/var/lib/nb-ems-central-sync/overflow_recovery_status.json"
REC_UP      = "/var/lib/nb-ems-central-sync/overflow_recovery_uploader_status.json"

STREAMS = [
    ("S1", "Fast BESS",       "fast_bess_telemetry"),
    ("S2", "General Assets",  "general_asset_telemetry"),
    ("S3", "Gateway Health",  "gateway_health"),
    ("S4", "Alarms / Events", "alarms_events"),
    ("S5", "SOC Controller",  "soc_controller"),
    ("S6", "Solis",           "solis"),
    ("S7", "Edge AI",         "edge_ai"),
    ("S8", "Config Audit",    "configuration_audit"),
]

def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}

def active(service):
    try:
        return subprocess.check_output(
            ["systemctl", "is-active", service],
            stderr=subprocess.DEVNULL,
            text=True
        ).strip()
    except Exception:
        return "unknown"

def iso_age(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())
    except Exception:
        return None

def age_txt(value):
    a = iso_age(value)
    if a is None:
        return "--"
    if a < 60:
        return f"{a:.1f}s"
    if a < 3600:
        return f"{a/60:.1f}m"
    return f"{a/3600:.1f}h"

def mb(v):
    try:
        return float(v or 0) / 1024 / 1024
    except Exception:
        return 0.0

def short(v, n=38):
    if not v:
        return "--"
    v = str(v)
    if len(v) <= n:
        return v
    return v[:n-3] + "..."

def archive_remaining(path):
    if not path or not os.path.exists(path):
        return None

    try:
        con = sqlite3.connect(
            f"file:{path}?mode=ro",
            uri=True,
            timeout=2
        )
        con.execute("PRAGMA query_only=ON")

        row = con.execute("""
            SELECT
                COUNT(*),
                COALESCE(SUM(payload_bytes),0)
            FROM outbox_messages
            WHERE state IN ('pending','retry','inflight')
        """).fetchone()

        states = {}
        for state, count, payload in con.execute("""
            SELECT
                state,
                COUNT(*),
                COALESCE(SUM(payload_bytes),0)
            FROM outbox_messages
            GROUP BY state
        """):
            states[str(state)] = (
                int(count or 0),
                int(payload or 0)
            )

        con.close()

        return {
            "messages": int(row[0] or 0),
            "bytes": int(row[1] or 0),
            "states": states,
        }

    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

while True:
    try:
        live = read_json(LIVE_STATUS)
        rec  = read_json(REC_STATUS)
        rup  = read_json(REC_UP)

        lu = live.get("uploader", {})
        lb = live.get("backend", {})
        lo = live.get("outbox", {})

        rc = rec.get("counters", {})
        ru = rup.get("uploader", {})
        rb = rup.get("backend", {})
        ro = rup.get("outbox", {})

        live_ack_age = iso_age(lu.get("last_success_utc"))
        replay_ack_age = iso_age(ru.get("last_success_utc"))

        live_ok = (
            lu.get("last_http_status") == 200
            and int(lu.get("request_success_count") or 0) > 0
            and live_ack_age is not None
            and live_ack_age < 120
        )

        replay_acked_msgs = (
            int(ru.get("accepted_count") or 0)
            + int(ru.get("already_processed_count") or 0)
        )

        replay_ok = (
            ru.get("last_http_status") == 200
            and int(ru.get("request_success_count") or 0) > 0
            and replay_acked_msgs > 0
            and replay_ack_age is not None
            and replay_ack_age < 120
        )

        archive = rc.get("last_archive_path")
        astat = archive_remaining(archive)

        os.system("clear")

        print("=" * 96)
        print("      NORTHBOUND EMS - LIVE + OVERFLOW/BACKLOG BACKEND PROOF DASHBOARD")
        print("=" * 96)
        print(" Time UTC       :", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
        print(" Central Sync   :", active("central-sync.service"))
        print(" Cloudflared    :", active("cloudflared.service"))
        print(" Legacy Replay  :", active("central-sync-backlog-replay.service"))
        print()

        # ------------------------------------------------------------------
        # LIVE
        # ------------------------------------------------------------------

        print("=" * 96)
        print(" A. LIVE TELEMETRY -> BACKEND")
        print("=" * 96)

        print(
            " BACKEND ACK STATUS :",
            "YES - LIVE DATA ACCEPTED" if live_ok
            else "NO RECENT CONFIRMED LIVE ACK"
        )

        print(" Last HTTP status   :", lu.get("last_http_status"))
        print(" Last success age   :", age_txt(lu.get("last_success_utc")))
        print(" Last success UTC   :", lu.get("last_success_utc") or "--")
        print(" Last request ID    :", lu.get("last_request_id") or "--")
        print(" Last error         :", lu.get("last_error") or "--")
        print()

        print(" Live requests OK   :", lu.get("request_success_count", 0))
        print(" Live requests FAIL :", lu.get("request_failure_count", 0))
        print(" Live accepted msgs :", lu.get("accepted_count", 0))
        print(" Already processed  :", lu.get("already_processed_count", 0))
        print(" Live bytes sent    : %.2f MB" % mb(lu.get("bytes_sent_uncompressed")))
        print()

        print(" Backend auth OK    :", lb.get("auth_success_count", 0))
        print(" Backend auth FAIL  :", lb.get("auth_failure_count", 0))
        print(" HTTP client resets :", lb.get("http_client_recreate_count", 0))
        print()

        print(" Live outbox:")
        print("   pending          :", lo.get("pending_count", 0))
        print("   retry            :", lo.get("retry_count", 0))
        print("   inflight         :", lo.get("inflight_count", 0))
        print("   unacked          :", lo.get("unacked_count", 0))
        print("   sendable payload : %.2f MB" % mb(lo.get("sendable_bytes")))
        print(
            "   oldest age       :",
            "%.1f sec" % float(lo.get("oldest_sendable_age_sec") or 0)
        )

        print()
        print(" Per-stream LIVE backend ACKs:")
        print(
            " %-3s %-19s %10s %10s %-20s" %
            ("ID", "Stream", "ACKs", "AckAge", "Last result")
        )
        print(
            " %-3s %-19s %10s %10s %-20s" %
            ("---", "-------------------", "----------", "----------", "--------------------")
        )

        stream_ack = live.get("stream_backend_ack", {})

        for sid, label, key in STREAMS:
            x = stream_ack.get(key, {})
            acked = int(x.get("acked_count") or 0)
            aage = age_txt(x.get("last_ack_utc"))
            result = x.get("last_backend_result") or "--"

            print(
                " %-3s %-19s %10d %10s %-20s" %
                (sid, label, acked, aage, short(result, 20))
            )

        # ------------------------------------------------------------------
        # BACKLOG / OVERFLOW
        # ------------------------------------------------------------------

        print()
        print("=" * 96)
        print(" B. OVERFLOW / BACKLOG REPLAY -> BACKEND")
        print("=" * 96)

        print(
            " BACKEND ACK STATUS :",
            "YES - BACKLOG DATA ACCEPTED" if replay_ok
            else "NO RECENT CONFIRMED BACKLOG ACK"
        )

        print(" Recovery running   :", rec.get("running"))
        print(" Paused reason      :", rc.get("last_pause_reason") or "--")
        print(" Recovery failures  :", rc.get("failure_count", 0))
        print(" Replay cycles      :", rc.get("request_cycle_count", 0))
        print(" Archives drained   :", rc.get("archive_drained_count", 0))
        print()

        print(" Current archive    :", archive or "--")
        print(" Recovery success   :", rc.get("last_success_utc") or "--")
        print(" Recovery success age:", age_txt(rc.get("last_success_utc")))
        print()

        print(" BACKLOG LAST REQUEST TO BACKEND")
        print(" -------------------------------")
        print(" HTTP status        :", ru.get("last_http_status"))
        print(" Request ID         :", ru.get("last_request_id") or "--")
        print(" Request success    :", ru.get("request_success_count", 0))
        print(" Request failure    :", ru.get("request_failure_count", 0))
        print(" Accepted messages  :", ru.get("accepted_count", 0))
        print(" Already processed  :", ru.get("already_processed_count", 0))
        print(" ACKed messages     :", replay_acked_msgs)
        print(" Payload sent       : %.3f MB" % mb(ru.get("bytes_sent_uncompressed")))
        print(" Last ACK UTC       :", ru.get("last_success_utc") or "--")
        print(" Last ACK age       :", age_txt(ru.get("last_success_utc")))
        print(" Last error         :", ru.get("last_error") or "--")
        print()

        if astat:
            if "error" in astat:
                print(" Archive DB status  :", astat["error"])
            else:
                print(" Current archive remaining:")
                print("   unsent messages  :", astat["messages"])
                print("   unsent payload   : %.2f MB" % mb(astat["bytes"]))

                for state in ("pending", "retry", "inflight"):
                    count, payload = astat["states"].get(state, (0, 0))
                    if count:
                        print(
                            "   %-8s        : %d msgs / %.2f MB" %
                            (state, count, mb(payload))
                        )

        print()
        print(" Backlog stream ACKs from LAST replay request:")
        print(
            " %-3s %-19s %10s %-10s %-20s" %
            ("ID", "Stream", "ACKs", "Status", "Last result")
        )
        print(
            " %-3s %-19s %10s %-10s %-20s" %
            ("---", "-------------------", "----------", "----------", "--------------------")
        )

        replay_streams = rup.get("stream_backend_ack", {})

        for sid, label, key in STREAMS:
            x = replay_streams.get(key)
            if not x:
                continue

            acked = int(x.get("acked_count") or 0)
            status = x.get("last_ack_status") or "--"
            result = x.get("last_backend_result") or "--"

            print(
                " %-3s %-19s %10d %-10s %-20s" %
                (
                    sid,
                    label,
                    acked,
                    short(status, 10),
                    short(result, 20)
                )
            )

        # ------------------------------------------------------------------
        # SUMMARY
        # ------------------------------------------------------------------

        print()
        print("=" * 96)
        print(" C. END-TO-END VERDICT")
        print("=" * 96)

        print(
            " LIVE TELEMETRY -> BACKEND :",
            "PASS" if live_ok else "NOT CONFIRMED NOW"
        )

        print(
            " BACKLOG DATA   -> BACKEND :",
            "PASS" if replay_ok else "NOT CONFIRMED NOW"
        )

        if live_ok and replay_ok:
            print()
            print(" BOTH LIVE + BACKLOG ARE CURRENTLY RECEIVING BACKEND ACKs.")
            print(" Give the two Request IDs above to backend team for server-log verification.")

        print()
        print(" Refresh every 5 sec. Ctrl+C to exit.")
        print("=" * 96)

        time.sleep(5)

    except KeyboardInterrupt:
        print()
        break

    except Exception as e:
        print("Dashboard error:", type(e).__name__, str(e))
        time.sleep(5)

PY
