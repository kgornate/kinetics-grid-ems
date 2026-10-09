#!/bin/sh
exec python3 - <<'PY'
import os
import re
import json
import time
import sqlite3
import subprocess
from collections import deque
from datetime import datetime, timezone, timedelta
from pathlib import Path

LIVE_STATUS = "/var/lib/nb-ems-central-sync/status.json"
REC_STATUS  = "/var/lib/nb-ems-central-sync/overflow_recovery_status.json"
REC_UP      = "/var/lib/nb-ems-central-sync/overflow_recovery_uploader_status.json"

IST = timezone(timedelta(hours=5, minutes=30))

REFRESH_SEC = 2.0
WINDOW_SEC  = 60.0

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

STREAM_LABELS = {key: (sid, label) for sid, label, key in STREAMS}


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def service_state(name):
    try:
        p = subprocess.run(
            ["systemctl", "is-active", name],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        )
        return p.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def dt_from_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except Exception:
        return None


def fmt_ist(value):
    dt = dt_from_iso(value)
    if dt is None:
        return "--"
    return dt.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S IST")


def fmt_epoch_ist(value):
    if value is None:
        return "--"
    try:
        return datetime.fromtimestamp(
            float(value), timezone.utc
        ).astimezone(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    except Exception:
        return "--"


def age_txt(value):
    dt = dt_from_iso(value)
    if dt is None:
        return "--"

    sec = max(
        0.0,
        (datetime.now(timezone.utc) - dt).total_seconds()
    )

    if sec < 60:
        return f"{sec:.1f}s"
    if sec < 3600:
        return f"{sec/60:.1f}m"
    return f"{sec/3600:.1f}h"


def mb(value):
    try:
        return float(value or 0) / 1024.0 / 1024.0
    except Exception:
        return 0.0


def short(value, length=28):
    if value is None:
        return "--"
    value = str(value)
    if len(value) <= length:
        return value
    return value[:length-3] + "..."


def archive_bucket(path):
    if not path:
        return "--"

    name = os.path.basename(path)

    m = re.search(
        r"central_sync_overflow_(\d{8}T\d{2})\.db$",
        name
    )

    if not m:
        return "--"

    try:
        start = datetime.strptime(
            m.group(1), "%Y%m%dT%H"
        ).replace(tzinfo=timezone.utc)

        end = start + timedelta(hours=1)

        return (
            start.astimezone(IST).strftime("%Y-%m-%d %H:%M")
            + " -> "
            + end.astimezone(IST).strftime("%H:%M IST")
        )

    except Exception:
        return "--"


def archive_info(path):
    result = {
        "messages": None,
        "bytes": None,
        "oldest": None,
        "newest": None,
        "streams": [],
        "error": None,
    }

    if not path or not os.path.exists(path):
        return result

    try:
        con = sqlite3.connect(
            f"file:{path}?mode=ro",
            uri=True,
            timeout=2.0,
        )

        con.execute("PRAGMA query_only=ON")
        con.execute("PRAGMA busy_timeout=2000")

        row = con.execute("""
            SELECT
                COUNT(*),
                COALESCE(SUM(payload_bytes), 0),
                MIN(created_epoch),
                MAX(created_epoch)
            FROM outbox_messages
            WHERE state IN ('pending','retry','inflight')
        """).fetchone()

        result["messages"] = int(row[0] or 0)
        result["bytes"] = int(row[1] or 0)
        result["oldest"] = row[2]
        result["newest"] = row[3]

        try:
            rows = con.execute("""
                SELECT
                    stream,
                    COUNT(*),
                    COALESCE(SUM(payload_bytes),0),
                    MIN(created_epoch),
                    MAX(created_epoch)
                FROM outbox_messages
                WHERE state IN ('pending','retry','inflight')
                GROUP BY stream
                ORDER BY COUNT(*) DESC
            """).fetchall()

            for r in rows:
                result["streams"].append({
                    "stream": str(r[0]),
                    "count": int(r[1] or 0),
                    "bytes": int(r[2] or 0),
                    "oldest": r[3],
                    "newest": r[4],
                })

        except Exception:
            pass

        con.close()

    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"

    return result


# ----------------------------------------------------------------------
# Rolling throughput state
# ----------------------------------------------------------------------

live_history = deque()
backlog_events = {}

start_mono = time.monotonic()

last_live_bytes = None

archive_cache = {}
archive_cache_time = 0.0
service_cache = {}
service_cache_time = 0.0


def prune(now):
    while live_history and now - live_history[0]["t"] > WINDOW_SEC:
        live_history.popleft()

    stale = [
        rid for rid, e in backlog_events.items()
        if now - e["t"] > WINDOW_SEC
    ]

    for rid in stale:
        backlog_events.pop(rid, None)


def update_throughput(live, replay, now):
    global last_live_bytes

    lu = live.get("uploader", {})
    ru = replay.get("uploader", {})

    current_live_bytes = int(
        lu.get("bytes_sent_uncompressed") or 0
    )

    current_live_ok = int(
        lu.get("request_success_count") or 0
    )

    current_live_fail = int(
        lu.get("request_failure_count") or 0
    )

    if (
        last_live_bytes is not None
        and current_live_bytes < last_live_bytes
    ):
        live_history.clear()

    last_live_bytes = current_live_bytes

    live_history.append({
        "t": now,
        "bytes": current_live_bytes,
        "ok": current_live_ok,
        "fail": current_live_fail,
    })

    # Recovery uploader is recreated for each replay cycle.
    # Track each unique Request ID independently.
    rid = ru.get("last_request_id")

    if rid:
        replay_bytes = int(
            ru.get("bytes_sent_uncompressed") or 0
        )

        replay_ok = (
            ru.get("last_http_status") == 200
            and int(ru.get("request_success_count") or 0) > 0
        )

        replay_fail = (
            int(ru.get("request_failure_count") or 0) > 0
        )

        accepted = (
            int(ru.get("accepted_count") or 0)
            + int(ru.get("already_processed_count") or 0)
        )

        if rid not in backlog_events:
            backlog_events[rid] = {
                "t": now,
                "bytes": replay_bytes,
                "ok": replay_ok,
                "fail": replay_fail,
                "accepted": accepted,
            }
        else:
            e = backlog_events[rid]

            # Keep first-seen timestamp but update final status.
            e["bytes"] = max(e["bytes"], replay_bytes)
            e["ok"] = replay_ok
            e["fail"] = replay_fail
            e["accepted"] = max(e["accepted"], accepted)

    prune(now)


def throughput(now):
    elapsed_from_start = max(
        1.0,
        min(WINDOW_SEC, now - start_mono)
    )

    live_mbpm = 0.0
    live_ok_pm = 0.0
    live_fail_pm = 0.0

    if len(live_history) >= 2:
        first = live_history[0]
        last = live_history[-1]

        dt = max(1.0, last["t"] - first["t"])

        delta_bytes = max(
            0,
            last["bytes"] - first["bytes"]
        )

        delta_ok = max(
            0,
            last["ok"] - first["ok"]
        )

        delta_fail = max(
            0,
            last["fail"] - first["fail"]
        )

        live_mbpm = (
            delta_bytes / 1024 / 1024
        ) * (60.0 / dt)

        live_ok_pm = delta_ok * (60.0 / dt)
        live_fail_pm = delta_fail * (60.0 / dt)

    backlog_wire_bytes = 0
    backlog_ack_bytes = 0
    backlog_ok = 0
    backlog_fail = 0
    backlog_acked_msgs = 0

    for e in backlog_events.values():
        backlog_wire_bytes += e["bytes"]

        if e["ok"]:
            backlog_ack_bytes += e["bytes"]
            backlog_ok += 1
            backlog_acked_msgs += e["accepted"]

        if e["fail"]:
            backlog_fail += 1

    backlog_wire_mbpm = (
        backlog_wire_bytes / 1024 / 1024
    ) * (60.0 / elapsed_from_start)

    backlog_ack_mbpm = (
        backlog_ack_bytes / 1024 / 1024
    ) * (60.0 / elapsed_from_start)

    backlog_req_pm = (
        backlog_ok * 60.0 / elapsed_from_start
    )

    backlog_fail_pm = (
        backlog_fail * 60.0 / elapsed_from_start
    )

    total_wire_mbpm = live_mbpm + backlog_wire_mbpm

    return {
        "live_mbpm": live_mbpm,
        "live_ok_pm": live_ok_pm,
        "live_fail_pm": live_fail_pm,

        "backlog_wire_mbpm": backlog_wire_mbpm,
        "backlog_ack_mbpm": backlog_ack_mbpm,
        "backlog_req_pm": backlog_req_pm,
        "backlog_fail_pm": backlog_fail_pm,
        "backlog_acked_msgs": backlog_acked_msgs,

        "total_wire_mbpm": total_wire_mbpm,
        "window": elapsed_from_start,
    }


while True:
    try:
        now = time.monotonic()

        live = read_json(LIVE_STATUS)
        rec = read_json(REC_STATUS)
        rup = read_json(REC_UP)

        update_throughput(live, rup, now)

        rates = throughput(now)

        lu = live.get("uploader", {})
        lb = live.get("backend", {})
        lo = live.get("outbox", {})

        rc = rec.get("counters", {})

        ru = rup.get("uploader", {})
        rb = rup.get("backend", {})
        ro = rup.get("outbox", {})

        live_ack_age = dt_from_iso(
            lu.get("last_success_utc")
        )

        replay_ack_age = dt_from_iso(
            ru.get("last_success_utc")
        )

        now_utc = datetime.now(timezone.utc)

        live_recent = (
            live_ack_age is not None
            and (now_utc - live_ack_age).total_seconds() < 120
        )

        replay_recent = (
            replay_ack_age is not None
            and (now_utc - replay_ack_age).total_seconds() < 120
        )

        live_ok = (
            lu.get("last_http_status") == 200
            and int(lu.get("request_success_count") or 0) > 0
            and live_recent
        )

        replay_acked_msgs = (
            int(ru.get("accepted_count") or 0)
            + int(ru.get("already_processed_count") or 0)
        )

        replay_ok = (
            ru.get("last_http_status") == 200
            and int(ru.get("request_success_count") or 0) > 0
            and replay_acked_msgs > 0
            and replay_recent
        )

        archive = rc.get("last_archive_path")

        # Heavy SQLite archive query only every ~10 sec or archive change.
        if (
            now - archive_cache_time > 10
            or archive_cache.get("_path") != archive
        ):
            archive_cache = archive_info(archive)
            archive_cache["_path"] = archive
            archive_cache_time = now

        # Service state only every 10 sec.
        if now - service_cache_time > 10:
            service_cache = {
                "central": service_state("central-sync.service"),
                "cloudflare": service_state("cloudflared.service"),
                "legacy": service_state(
                    "central-sync-backlog-replay.service"
                ),
            }
            service_cache_time = now

        os.system("clear")

        print("=" * 108)
        print("        NORTHBOUND EMS - LIVE + BACKLOG BACKEND / THROUGHPUT DASHBOARD")
        print("=" * 108)

        print(
            " Time IST       :",
            datetime.now(IST).strftime(
                "%Y-%m-%d %H:%M:%S IST"
            )
        )

        print(
            " Central Sync   :",
            service_cache.get("central", "--"),
            " | Cloudflare:",
            service_cache.get("cloudflare", "--"),
            " | Legacy Replay:",
            service_cache.get("legacy", "--")
        )

        print()

        # ==============================================================
        # THROUGHPUT
        # ==============================================================

        print("=" * 108)
        print(" A. GATEWAY -> BACKEND THROUGHPUT")
        print("=" * 108)

        print(
            " Rolling window              : %.0f sec"
            % rates["window"]
        )

        print(
            " LIVE upload                 : %6.2f MB/min"
            % rates["live_mbpm"]
        )

        print(
            " BACKLOG upload observed     : %6.2f MB/min"
            % rates["backlog_wire_mbpm"]
        )

        print(
            " BACKLOG backend-ACKed       : %6.2f MB/min"
            % rates["backlog_ack_mbpm"]
        )

        print(
            " ----------------------------------------------------------------"
        )

        print(
            " TOTAL gateway -> backend    : %6.2f MB/min"
            % rates["total_wire_mbpm"]
        )

        print()

        print(
            " Live request rate           : %6.1f OK/min | %5.1f FAIL/min"
            % (
                rates["live_ok_pm"],
                rates["live_fail_pm"]
            )
        )

        print(
            " Backlog observed request rate: %5.1f OK/min | %5.1f FAIL/min"
            % (
                rates["backlog_req_pm"],
                rates["backlog_fail_pm"]
            )
        )

        if rates["live_fail_pm"] == 0:
            print(
                " Live window status          : all observed requests successful"
            )
        else:
            print(
                " Live window status          : failures present; LIVE MB/min above is wire/attempted rate"
            )

        print()

        # ==============================================================
        # LIVE
        # ==============================================================

        print("=" * 108)
        print(" B. LIVE TELEMETRY -> BACKEND")
        print("=" * 108)

        print(
            " BACKEND ACK STATUS :",
            "PASS - LIVE DATA ACCEPTED"
            if live_ok
            else "NO RECENT CONFIRMED LIVE ACK"
        )

        print(" HTTP status        :", lu.get("last_http_status"))
        print(" Last ACK IST       :", fmt_ist(lu.get("last_success_utc")))
        print(" Last ACK age       :", age_txt(lu.get("last_success_utc")))
        print(" Request ID         :", lu.get("last_request_id") or "--")
        print(" Last error         :", lu.get("last_error") or "--")

        print()

        print(
            " Live accepted      :",
            lu.get("accepted_count", 0),
            "messages"
        )

        print(
            " Live requests      :",
            lu.get("request_success_count", 0),
            "OK /",
            lu.get("request_failure_count", 0),
            "FAIL"
        )

        print(
            " Live cumulative TX : %.2f MB"
            % mb(lu.get("bytes_sent_uncompressed"))
        )

        print(
            " Live queue         : %s unacked | %.2f MB | oldest %.1f sec"
            % (
                lo.get("unacked_count", 0),
                mb(lo.get("sendable_bytes")),
                float(
                    lo.get("oldest_sendable_age_sec") or 0
                ),
            )
        )

        print()

        print(
            " %-3s %-20s %10s %10s %-20s"
            % (
                "ID",
                "LIVE Stream",
                "ACKs",
                "AckAge",
                "Last result",
            )
        )

        print(
            " %-3s %-20s %10s %10s %-20s"
            % (
                "---",
                "--------------------",
                "----------",
                "----------",
                "--------------------",
            )
        )

        live_streams = live.get("stream_backend_ack", {})

        for sid, label, key in STREAMS:
            x = live_streams.get(key, {})

            print(
                " %-3s %-20s %10d %10s %-20s"
                % (
                    sid,
                    label,
                    int(x.get("acked_count") or 0),
                    age_txt(x.get("last_ack_utc")),
                    short(
                        x.get("last_backend_result") or "--",
                        20
                    ),
                )
            )

        print()

        # ==============================================================
        # BACKLOG
        # ==============================================================

        print("=" * 108)
        print(" C. OVERFLOW / BACKLOG REPLAY -> BACKEND")
        print("=" * 108)

        print(
            " BACKEND ACK STATUS :",
            "PASS - BACKLOG DATA ACCEPTED"
            if replay_ok
            else "NO RECENT CONFIRMED BACKLOG ACK"
        )

        print(" Recovery running   :", rec.get("running"))
        print(" Paused reason      :", rc.get("last_pause_reason") or "--")
        print(" Replay cycles      :", rc.get("request_cycle_count", 0))
        print(" Replay failures    :", rc.get("failure_count", 0))
        print(" Archives drained   :", rc.get("archive_drained_count", 0))

        print()

        print(" Current archive:")
        print("   DB               :", archive or "--")
        print("   Archive hour IST :", archive_bucket(archive))

        if archive_cache.get("error"):
            print(
                "   DB read error    :",
                archive_cache["error"]
            )
        else:
            print(
                "   Remaining        : %s messages / %.2f MB"
                % (
                    archive_cache.get("messages", "--"),
                    mb(archive_cache.get("bytes")),
                )
            )

            print(
                "   Oldest data IST  :",
                fmt_epoch_ist(archive_cache.get("oldest"))
            )

            print(
                "   Newest data IST  :",
                fmt_epoch_ist(archive_cache.get("newest"))
            )

        print()

        print(" LAST BACKLOG REQUEST -> BACKEND")
        print(" --------------------------------")

        print(" HTTP status        :", ru.get("last_http_status"))
        print(" Request ID         :", ru.get("last_request_id") or "--")
        print(" Request success    :", ru.get("request_success_count", 0))
        print(" Request failure    :", ru.get("request_failure_count", 0))
        print(" Accepted messages  :", ru.get("accepted_count", 0))
        print(" Already processed  :", ru.get("already_processed_count", 0))
        print(" ACKed messages     :", replay_acked_msgs)
        print(
            " Request payload    : %.3f MB"
            % mb(ru.get("bytes_sent_uncompressed"))
        )
        print(" Backend ACK IST    :", fmt_ist(ru.get("last_success_utc")))
        print(" Backend ACK age    :", age_txt(ru.get("last_success_utc")))
        print(" Last error         :", ru.get("last_error") or "--")

        print()

        print(
            " Streams in LAST replay request accepted by backend:"
        )

        print(
            " %-3s %-20s %6s %12s %-18s %-10s"
            % (
                "ID",
                "Stream",
                "ACKs",
                "Sequence",
                "Substream",
                "Status",
            )
        )

        print(
            " %-3s %-20s %6s %12s %-18s %-10s"
            % (
                "---",
                "--------------------",
                "------",
                "------------",
                "------------------",
                "----------",
            )
        )

        replay_streams = rup.get("stream_backend_ack", {})

        if not replay_streams:
            print(" No stream ACK information in latest replay request.")
        else:
            for sid, label, key in STREAMS:
                x = replay_streams.get(key)

                if not x:
                    continue

                print(
                    " %-3s %-20s %6d %12s %-18s %-10s"
                    % (
                        sid,
                        label,
                        int(x.get("acked_count") or 0),
                        str(
                            x.get("last_ack_sequence")
                            if x.get("last_ack_sequence") is not None
                            else "--"
                        ),
                        short(
                            x.get("last_ack_substream") or "--",
                            18
                        ),
                        short(
                            x.get("last_ack_status") or "--",
                            10
                        ),
                    )
                )

        print()

        if archive_cache.get("streams"):
            print(
                " Current archive REMAINING stream/data-time inventory:"
            )

            print(
                " %-3s %-20s %8s %9s %-20s %-20s"
                % (
                    "ID",
                    "Stream",
                    "Msgs",
                    "MB",
                    "Oldest IST",
                    "Newest IST",
                )
            )

            print(
                " %-3s %-20s %8s %9s %-20s %-20s"
                % (
                    "---",
                    "--------------------",
                    "--------",
                    "---------",
                    "--------------------",
                    "--------------------",
                )
            )

            for s in archive_cache["streams"]:
                sid, label = STREAM_LABELS.get(
                    s["stream"],
                    ("--", s["stream"])
                )

                old_t = fmt_epoch_ist(s["oldest"]).replace(
                    " IST", ""
                )

                new_t = fmt_epoch_ist(s["newest"]).replace(
                    " IST", ""
                )

                print(
                    " %-3s %-20s %8d %9.2f %-20s %-20s"
                    % (
                        sid,
                        short(label, 20),
                        s["count"],
                        mb(s["bytes"]),
                        short(old_t, 20),
                        short(new_t, 20),
                    )
                )

        print()

        # ==============================================================
        # VERDICT
        # ==============================================================

        print("=" * 108)
        print(" D. END-TO-END STATUS")
        print("=" * 108)

        print(
            " LIVE TELEMETRY -> BACKEND :",
            "PASS" if live_ok else "NOT CONFIRMED"
        )

        print(
            " BACKLOG DATA   -> BACKEND :",
            "PASS" if replay_ok else "NOT CONFIRMED"
        )

        print(
            " TOTAL GATEWAY TX          : %.2f MB/min"
            % rates["total_wire_mbpm"]
        )

        print(
            " BACKLOG ACKED RATE        : %.2f MB/min"
            % rates["backlog_ack_mbpm"]
        )

        if live_ok and replay_ok:
            print()
            print(
                " BOTH LIVE AND HISTORICAL BACKLOG DATA ARE CURRENTLY RECEIVING BACKEND ACKs."
            )

        print()
        print(
            " Note: throughput uses a rolling observed window; it stabilizes after ~60 sec."
        )
        print(
            " Backlog data timestamps above come from created_epoch inside the current overflow DB."
        )
        print(
            " Refresh every %.0f sec. Ctrl+C to exit."
            % REFRESH_SEC
        )

        print("=" * 108)

        time.sleep(REFRESH_SEC)

    except KeyboardInterrupt:
        print()
        break

    except Exception as e:
        print(
            "Dashboard error:",
            type(e).__name__,
            str(e)
        )
        time.sleep(REFRESH_SEC)

PY
