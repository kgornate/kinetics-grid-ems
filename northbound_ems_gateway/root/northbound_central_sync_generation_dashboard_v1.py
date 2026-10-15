#!/usr/bin/env python3
"""Northbound Central Sync - live DATA GENERATION / S2 CADENCE dashboard.

Read-only: queries newly enqueued message metadata + record counts from the live
SQLite outbox (mode=ro, query_only=ON); reads gateway status JSON and filesystem
metadata. No network requests, no services changes, no archive DB payload scans.

Run: python3 -u northbound_central_sync_generation_dashboard_v1.py
Stop: Ctrl+C. First 60 seconds warm up the rolling rate window.
"""
from __future__ import annotations

import argparse
import collections
from contextlib import closing
from datetime import datetime, timezone, timedelta
import json
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import time
from urllib.parse import quote

MIB = 1024 * 1024
KIB = 1024
STREAMS = [
    ("S1", "fast_bess_telemetry", "Fast BESS"),
    ("S2", "general_asset_telemetry", "General Assets"),
    ("S3", "gateway_health", "Gateway Health"),
    ("S4", "alarms_events", "Alarms / Events"),
    ("S5", "soc_controller", "SOC Controller"),
    ("S6", "solis", "Solis"),
    ("S7", "edge_ai", "Edge AI"),
    ("S8", "configuration_audit", "Configuration"),
    ("S9", "command_results", "Command Results"),
]
S2_SUBSTREAMS = [
    "ems_system", "pcs_extended", "bms_extended", "io_module",
    "liquid_cooling", "fire_protection", "dehumidifier", "remote_control", "utility_meter",
]
PARTITIONS = [(stream, sub) for _id, stream, _name in STREAMS
              for sub in (S2_SUBSTREAMS if stream == "general_asset_telemetry"
                          else (["bess", ""] if stream == "fast_bess_telemetry" else [""]))]


def read_dict(p):
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except (OSError, ValueError):
        return {}


def number(obj, key):
    if not isinstance(obj, dict):
        return None
    val = obj.get(key)
    return val if isinstance(val, (int, float)) and not isinstance(val, bool) else None


def ro_connect(path):
    uri = "file:" + quote(str(path), safe="/") + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=1.0)
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA busy_timeout=750")
    return conn


def pick_window(events, now, period):
    cutoff = max(0.0, now - period)
    return [e for e in events if e[0] >= cutoff]


def rate_amount(events, now, period, elapsed):
    used_minutes = max(1 / 60, min(period, elapsed) / 60)
    return used_minutes, pick_window(events, now, period)


def as_rate(n, minutes):
    return float(n) / max(minutes, 1 / 60)


def delta_counters(history, now, period, key, field="s2"):
    if not history:
        return None, None
    newest = history[-1]
    selected = history[0]
    cutoff = now - period
    for entry in history:
        if entry[0] <= cutoff:
            selected = entry
        else:
            break
    older_value = number(selected[1][field], key)
    newer_value = number(newest[1][field], key)
    seconds = max(1.0, newest[0] - selected[0])
    if older_value is None or newer_value is None or newer_value < older_value:
        return None, seconds
    return newer_value - older_value, seconds


def mib(x):
    return float(x) / MIB


def scan_archive_sizes(path):
    # Metadata-only; no archive database reads. Frequency throttled by caller.
    size = 0
    files = 0
    try:
        for base, _dirs, filenames in os.walk(path):
            for filename in filenames:
                p = os.path.join(base, filename)
                try:
                    s = os.stat(p, follow_symlinks=False)
                    if os.path.isfile(p):
                        size += s.st_size
                        files += 1
                except OSError:
                    continue
    except OSError:
        return None, None
    return size, files


class Dashboard:
    def __init__(self, args):
        self.args = args
        self.started_wall = time.time()
        self.started_mono = time.monotonic()
        self.events = collections.deque()
        self.seen = {}
        self.history = collections.deque()
        self.errors = 0
        self.last_error = ""
        self.last_db_scan = 0.0
        self.last_storage_check = 0.0
        self.disk_initial = None
        self.disk_current = None
        self.archive_initial = None
        self.archive_current = None
        self.archive_files = None
        self.initial_s2_start = None
        self.initial_policy_sha = None
        self.new_s2_max = 0
        self.cap_violations = 0
        self.scanned = 0
        self.last_gap = None
        self.initial_snapshot = read_dict(args.status_dir / "general_asset_producer_status.json")
        self.initial_policy_sha = self.initial_snapshot.get("policy_manifest_sha256")
        self.initial_s2_start = self.initial_snapshot.get("started_utc")
        self.manifest = read_dict(args.manifest)
        self.manifest_sha = None
        try:
            self.manifest_sha = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
        except OSError:
            pass
        self._storage_update(force=True)

    def _storage_update(self, force=False):
        now = time.monotonic()
        if not force and now - self.last_storage_check < 20:
            return
        self.last_storage_check = now
        try:
            v = os.statvfs(str(self.args.mount))
            total = v.f_blocks * v.f_frsize
            available = v.f_bavail * v.f_frsize
            used = (v.f_blocks - v.f_bfree) * v.f_frsize
            self.disk_current = (total, used, available)
            if self.disk_initial is None:
                self.disk_initial = self.disk_current
        except OSError:
            self.disk_current = None
        ab, af = scan_archive_sizes(self.args.archive_dir)
        self.archive_current = ab
        self.archive_files = af
        if self.archive_initial is None:
            self.archive_initial = ab

    def scan_sqlite(self):
        now = time.time()
        if self.last_db_scan:
            self.last_gap = now - self.last_db_scan
        self.last_db_scan = now
        # This 40s lookback stays inside the age-to-overflow window (~60s).
        # Query each (stream, substream) via the actual covering index
        # idx_outbox_stream(stream,substream,created_epoch).
        since = max(self.started_wall, now - 40)
        try:
            with closing(ro_connect(self.args.db)) as con:
                for stream, substream in PARTITIONS:
                    rows = con.execute(
                        "SELECT message_id,created_epoch,payload_bytes,payload_json "
                        "FROM outbox_messages "
                        "WHERE stream=? AND substream=? AND created_epoch>=? AND created_epoch<=?",
                        (stream, substream, since, now + 2),
                    )
                    for mid, created, bytelen, payload in rows:
                        if mid in self.seen:
                            continue
                        if created is None or float(created) < self.started_wall:
                            continue
                        self.seen[mid] = now
                        records = 0
                        triggers = collections.Counter()
                        if stream == "general_asset_telemetry":
                            try:
                                msg = json.loads(payload)
                                signal_rows = msg.get("records", []) if isinstance(msg, dict) else []
                                if isinstance(signal_rows, list):
                                    records = len(signal_rows)
                                    for rec in signal_rows:
                                        if isinstance(rec, dict):
                                            triggers[str(rec.get("trigger_reason") or "unknown")] += 1
                            except (ValueError, TypeError):
                                triggers["parse_error"] += 1
                        else:
                            # Don't decode large non-S2 JSON: record counts aren't needed for this dashboard.
                            records = 0
                        try:
                            nbytes = int(bytelen)
                        except (ValueError, TypeError):
                            continue
                        self.events.append((float(created), stream, substream, nbytes, records, triggers))
                        if stream == "general_asset_telemetry":
                            self.new_s2_max = max(self.new_s2_max, nbytes)
                            if nbytes > 96 * KIB:
                                self.cap_violations += 1
                        self.scanned += 1
        except (sqlite3.Error, OSError) as exc:
            self.errors += 1
            self.last_error = (type(exc).__name__ + ": " + str(exc))[:125]
        # Retain slightly over 5m of windowed events; trim the ID cache too.
        cutoff = now - 330
        while self.events and self.events[0][0] < cutoff:
            self.events.popleft()
        if len(self.seen) > 10000 or self.scanned % 10 == 0:
            for key, seen_time in list(self.seen.items()):
                if seen_time < now - 120:
                    del self.seen[key]

    def snapshot_status(self):
        status = read_dict(self.args.status_dir / "general_asset_producer_status.json")
        arch = read_dict(self.args.status_dir / "overflow_archiver_status.json")
        central = read_dict(self.args.status_dir / "status.json")
        s2c = status.get("counters") or {}
        ac = arch.get("counters") or {}
        if not isinstance(s2c, dict):
            s2c = {}
        if not isinstance(ac, dict):
            ac = {}
        return {
            "s2": s2c, "arch": ac, "running": status.get("running"),
            "policy": status.get("policy_manifest_sha256"),
            "started": status.get("started_utc"),
            "outbox": central.get("outbox") or {},
        }

    def tick(self):
        self.scan_sqlite()
        now = time.time()
        s = self.snapshot_status()
        self.history.append((now, s))
        while self.history and self.history[0][0] < now - 350:
            self.history.popleft()
        self._storage_update()
        return self.render(now, s)

    def render(self, now, current):
        elapsed = max(0.001, now - self.started_wall)
        m1, ev1 = rate_amount(self.events, now, 60, elapsed)
        m5, ev5 = rate_amount(self.events, now, 300, elapsed)
        def aggregate(entries, groupby=None):
            d = collections.defaultdict(lambda: [0, 0, 0, 0])
            for _at, stream, sub, nbytes, nrec, _tr in entries:
                key = (stream, sub) if groupby == 'sub' else stream
                v = d[key]
                v[0] += 1
                v[1] += nbytes
                v[2] += nrec
                v[3] = max(v[3], nbytes)
            return d
        b1 = aggregate(ev1)
        b5 = aggregate(ev5)
        s1 = aggregate(ev1, 'sub')
        s5 = aggregate(ev5, 'sub')
        n1 = sum(v[0] for v in b1.values())
        t1 = sum(v[1] for v in b1.values())
        n5 = sum(v[0] for v in b5.values())
        t5 = sum(v[1] for v in b5.values())
        lines = []
        p = lines.append
        p('=' * 108)
        p('   NORTHBOUND EMS  |  LIVE DATA GENERATION & S2 CADENCE DASHBOARD  |  READ-ONLY')
        p('=' * 108)
        ist = datetime.fromtimestamp(now, timezone(timedelta(hours=5, minutes=30))).strftime('%Y-%m-%d %H:%M:%S IST')
        p(f' Time: {ist}  |  Refresh: {self.args.interval:g}s  |  Uptime: {elapsed/60:.1f} min')
        p(f' Sampling: SQLite mode=ro + status counters | Live window: {min(elapsed,60):.0f}/60s | Trend: {min(elapsed,300):.0f}/300s')
        if elapsed < 60:
            p(' NOTE: WARMING UP - 60-second rates become representative after 1 minute; 5-minute trend after 5 minutes.')
        p('')
        p(' A. GATEWAY NEW DATA GENERATION (NOT BACKEND TRANSMISSION)')
        p('-' * 108)
        p(f' ALL STREAMS: LIVE {mib(t1)/m1:7.3f} MiB/min | {n1/m1:7.1f} messages/min'
          f'   ||   5m: {mib(t5)/m5:7.3f} MiB/min | {n5/m5:7.1f} messages/min')
        for stream, label in [('general_asset_telemetry', 'S2 share'), ('fast_bess_telemetry', 'S1 share')]:
            v = b1.get(stream, (0, 0, 0, 0))
            share = 100 * v[1] / t1 if t1 else 0
            p(f' {label:<9}: {mib(v[1])/m1:7.3f} MiB/min | {v[0]/m1:7.1f} msg/min | {share:5.1f}% of generation (1m)')
        p('')
        p(' B. S1-S9 PER-STREAM NEW GENERATION')
        p('-' * 108)
        p(' ID  Stream               Messages/min          Uncompressed MiB/min       Avg size (KiB, 1m)')
        p('                          1m       5m            1m        5m')
        for sid, stream, label in STREAMS:
            v1 = b1.get(stream, (0, 0, 0, 0))
            v5 = b5.get(stream, (0, 0, 0, 0))
            avg = (v1[1] / v1[0] / 1024) if v1[0] else 0
            p(f' {sid:<3} {label:<19} {v1[0]/m1:7.2f} {v5[0]/m5:8.2f}'
              f'       {mib(v1[1])/m1:7.3f}   {mib(v5[1])/m5:7.3f}               {avg:7.1f}')
        p('')
        p(' C. S2 SUBSTREAMS: NEW MESSAGES, PAYLOAD & SIGNAL RECORDING')
        p('-' * 108)
        p(' Substream                 Msg/min (1m)   MiB/min (1m)   Signal records/sec (1m)   MiB/min (5m)')
        for sub in S2_SUBSTREAMS:
            x = s1.get(('general_asset_telemetry',sub), (0, 0, 0, 0))
            y = s5.get(('general_asset_telemetry',sub), (0, 0, 0, 0))
            p(f' {sub:<26} {x[0]/m1:9.2f}       {mib(x[1])/m1:8.3f}'
              f'            {x[2]/(m1*60):8.2f}              {mib(y[1])/m5:8.3f}')
        p('')
        p(' D. S2 CADENCE, RECORD TRIGGERS & SAFETY')
        p('-' * 108)
        modes = self.manifest.get('s2_policy_counts_canonical') or {}
        seconds = self.manifest.get('seconds_distribution_canonical') or {}
        if not seconds:
            seconds = self.manifest.get('s2_seconds_distribution_canonical') or {}
        if not seconds:
            seconds = collections.Counter(
                str(x['central_record_sec']) for x in self.manifest.get('signals', [])
                if isinstance(x, dict) and x.get('policy') in ('PERIODIC','ON_CHANGE_HEARTBEAT')
                and x.get('central_record_sec') is not None
            )
        if modes:
            p(' Frozen S2 points: PERIODIC=%s | ON_CHANGE_HEARTBEAT=%s | 1,350 canonical x 2 EMS' % (
                modes.get('PERIODIC','N/A'), modes.get('ON_CHANGE_HEARTBEAT','N/A')))
        if seconds:
            p(' Cadence distribution (canonical): ' + ' | '.join(f'{k}s:{v}' for k,v in sorted(seconds.items(), key=lambda item:int(item[0]))))
        if self.manifest_sha:
            p(' Manifest SHA matches active producer status: ' + str(self.manifest_sha == current['policy']) +
              ' | ' + self.manifest_sha[:16] + '...')
        def fmt_count_rate(key, period):
            val, seconds = delta_counters(self.history, now, period, key)
            return ('N/A' if val is None else f'{val/max(1.0,seconds):.2f}/sec')
        r1, sec1 = delta_counters(self.history, now, 60, 'record_count')
        r5, sec5 = delta_counters(self.history, now, 300, 'record_count')
        calc1 = f'{r1/max(sec1 or 1,1):.2f}' if r1 is not None else 'N/A'
        calc5 = f'{r5/max(sec5 or 1,1):.2f}' if r5 is not None else 'N/A'
        msg1, ms1 = delta_counters(self.history, now, 60, 'message_count')
        p(f' S2 records/sec (producer counters): {calc1} live  |  {calc5} over 5m  |  design quiet-period ~31.08/sec')
        p(' Triggers from producer counters (rolling 60s):')
        for label,key in [('PERIODIC','periodic_record_count'),('HEARTBEAT','heartbeat_record_count'),('CHANGE','change_record_count'),('STARTUP','startup_record_count')]:
            dv, secs = delta_counters(self.history, now, 60, key)
            p(f'   {label:<11}  {("N/A" if dv is None else str(int(dv))):>6} records   |  {("N/A" if dv is None else f"{dv/max(1,secs):.2f}"):>6} records/sec')
        s2_1 = b1.get('general_asset_telemetry', (0, 0, 0, 0))
        s2_5 = b5.get('general_asset_telemetry', (0, 0, 0, 0))
        maxkib = s2_5[3]/1024
        p(f' SQLite S2 signal records/sec: {s2_1[2]/(m1*60):.2f} (1m) | {s2_5[2]/(m5*60):.2f} (5m)')
        p(f' S2 logical message max in rolling 5m: {maxkib:.2f} KiB / 96 KiB cap'
          f' | Cap violations since launch: {self.cap_violations}')
        p(f' Producer running: {current["running"]} | Policy unchanged since dashboard start:'
          f' {bool(self.initial_policy_sha and current["policy"] == self.initial_policy_sha)}'
          f' | Producer restarted: {current["started"] != self.initial_s2_start}')
        for key in ('enqueue_failure_count','poll_failure_count','shape_rejection_count'):
            dv, _seconds = delta_counters(self.history, now, 300, key)
            p(f'   5m {key:<26} = {"N/A" if dv is None else int(dv)}')
        p('')
        p(' E. LOCAL QUEUE, OVERFLOW ARCHIVING & STORAGE')
        p('-' * 108)
        outbox = current.get('outbox') or {}
        sendable = number(outbox, "sendable_bytes")
        payload_display = "N/A" if sendable is None else f"{mib(sendable):.3f} MiB"
        p(f' Live unacked: {outbox.get("unacked_count","N/A")} messages'
          f' | Sendable payload: {payload_display}'
          f' | Oldest age: {outbox.get("oldest_age_sec","N/A")}s')
        archive_dv, archive_sec = delta_counters(self.history, now, 60, 'archived_payload_bytes', field='arch')
        arch_rate = 'N/A' if archive_dv is None else f'{mib(archive_dv)/(archive_sec/60):.3f}'
        p(f' Newly archived logical payload: {arch_rate} MiB/min (60s; counters, not remaining unsent)')
        if self.disk_current:
            total, used, free = self.disk_current
            p(f' /mnt/ems-logs: {used/MIB/1024:.2f} GiB used / {total/MIB/1024:.2f} GiB total'
              f' | free {free/MIB/1024:.2f} GiB | {100*used/total:.1f}% used')
            if self.disk_initial:
                disk_growth = used-self.disk_initial[1]
                p(f' Filesystem net growth since dashboard launch: {disk_growth/MIB:+.2f} MiB'
                  f' in {elapsed/60:.1f} min')
        if self.archive_current is not None:
            p(f' Archive directory: {self.archive_current/MIB/1024:.2f} GiB'
              f' | physical change since launch {((self.archive_current-(self.archive_initial or 0))/MIB):+.2f} MiB'
              f' | files {self.archive_files}')
        p(' Retained archive size is not equivalent to undelivered backlog.')
        p('')
        p(' F. MONITOR QUALITY')
        p('-' * 108)
        p(f' New outbox messages seen since launch: {self.scanned} | SQLite read errors: {self.errors}'
          f' | Last scan gap: {"N/A" if self.last_gap is None else f"{self.last_gap:.1f}s"}')
        if self.last_error:
            p(f' Last DB read error: {self.last_error}')
        if self.last_gap and self.last_gap > 25:
            p(' WARNING: long scan gap may undercount messages after overflow archival.')
        if current['started'] != self.initial_s2_start:
            p(' WARNING: S2 producer restarted; trigger counter rates may reset.')
        if self.cap_violations:
            p(' WARNING: observed at least one S2 logical message exceeding 96 KiB.')
        p(' Press Ctrl+C to exit. Dashboard only reads gateway state; does not change services or queues.')
        p('=' * 108)
        return '\n'.join(lines)


def main():
    pa = argparse.ArgumentParser(description=__doc__)
    pa.add_argument('--db',type=Path,default=Path('/mnt/ems-logs/northbound_ems_gateway/central_sync_outbox.db'))
    pa.add_argument('--manifest',type=Path,default=Path('/root/kinetics-grid-ems/northbound_ems_gateway/data/central_sync/canonical_signal_policy_frozen_v1_1.json'))
    pa.add_argument('--status-dir',type=Path,default=Path('/var/lib/nb-ems-central-sync'))
    pa.add_argument('--archive-dir',type=Path,default=Path('/mnt/ems-logs/northbound_ems_gateway/backlog_archives'))
    pa.add_argument('--mount',type=Path,default=Path('/mnt/ems-logs'))
    pa.add_argument('--interval',type=float,default=2)
    pa.add_argument('--no-clear',action='store_true',help='append frames instead of clearing (also when not a TTY)')
    pa.add_argument('--iterations',type=int,default=0,help='test only: stop after this many frames (0 = forever)')
    args = pa.parse_args()
    if args.interval < 0.5 or args.interval > 30:
        pa.error('interval must be in 0.5..30 seconds')
    if not args.db.is_file():
        print(f'ERROR: SQLite outbox not found: {args.db}',file=sys.stderr)
        return 2
    print('Starting read-only generation dashboard. Rates warm up over 60s / 300s.',flush=True)
    dash = Dashboard(args)
    iteration=0
    try:
        while True:
            screen=dash.tick()
            if sys.stdout.isatty() and not args.no_clear:
                sys.stdout.write('\033[H\033[2J')
            print(screen,flush=True)
            iteration+=1
            if args.iterations and iteration>=args.iterations:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print('\nGeneration dashboard stopped; gateway services unchanged.',flush=True)
    return 0


if __name__=='__main__':
    sys.exit(main())
