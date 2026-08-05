#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path


def read_kv(path: Path) -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                values[parts[0].rstrip(":")] = int(parts[1])
    except OSError:
        pass
    return values


def sample(pid: int) -> dict[str, object]:
    status = read_kv(Path(f"/proc/{pid}/status"))
    rollup = read_kv(Path(f"/proc/{pid}/smaps_rollup"))
    cgroup = {}
    try:
        line = next(x for x in Path(f"/proc/{pid}/cgroup").read_text().splitlines() if x.startswith("0::"))
        cg = Path("/sys/fs/cgroup") / line.partition("::")[2].lstrip("/")
        cgroup = read_kv(cg / "memory.stat")
        current = (cg / "memory.current").read_text().strip()
    except (OSError, StopIteration):
        current = None
    kib = lambda value: value * 1024 if value is not None else None
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pid": pid,
        "process": {
            "rss_bytes": kib(status.get("VmRSS")),
            "rss_anon_bytes": kib(status.get("RssAnon")),
            "rss_file_bytes": kib(status.get("RssFile")),
            "pss_bytes": kib(rollup.get("Pss")),
            "private_dirty_bytes": kib(rollup.get("Private_Dirty")),
            "threads": status.get("Threads"),
        },
        "cgroup": {
            "current_bytes": int(current) if current and current.isdigit() else None,
            "anon_bytes": cgroup.get("anon"),
            "file_bytes": cgroup.get("file"),
            "kernel_bytes": cgroup.get("kernel"),
            "sock_bytes": cgroup.get("sock"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded Kinetics gateway memory sampler")
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--samples", type=int, default=12)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    with output.open("w", encoding="utf-8") as handle:
        for index in range(max(1, min(args.samples, 360))):
            if not Path(f"/proc/{args.pid}").exists():
                break
            handle.write(json.dumps(sample(args.pid), separators=(",", ":")) + "\n")
            handle.flush()
            if index + 1 < args.samples:
                time.sleep(max(0.2, args.interval))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
