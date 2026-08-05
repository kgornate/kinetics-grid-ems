from __future__ import annotations

import resource
import threading
import time
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RuntimeMetrics:
    """Small, bounded, in-memory runtime measurements for field diagnostics."""

    def __init__(self, *, max_routes: int = 128, slow_request_ms: float = 2000.0) -> None:
        self._lock = threading.Lock()
        self._started_monotonic = time.monotonic()
        self._max_routes = max(1, int(max_routes))
        self.slow_request_ms = max(1.0, float(slow_request_ms))
        self._http_in_flight = 0
        self._http_peak_in_flight = 0
        self._http_admission = {
            "active": 0,
            "peak_active": 0,
            "active_general": 0,
            "active_priority": 0,
            "accepted": 0,
            "accepted_general": 0,
            "accepted_priority": 0,
            "rejected": 0,
            "rejected_general": 0,
            "rejected_priority": 0,
        }
        self._routes: dict[str, dict[str, Any]] = {}
        self._background: dict[str, dict[str, Any]] = {}
        self._websockets = {
            "active": 0,
            "peak_active": 0,
            "accepted": 0,
            "disconnected": 0,
            "send_failures": 0,
            "rejected_clients": 0,
            "send_timeouts": 0,
            "backpressure_disconnects": 0,
        }
        self._event_loop_lag_ms = 0.0
        self._event_loop_lag_peak_ms = 0.0
        self._asyncio_tasks = 0
        self._asyncio_tasks_peak = 0
        self._recent_slow_requests: deque[dict[str, Any]] = deque(maxlen=20)

    def request_started(self) -> None:
        with self._lock:
            self._http_in_flight += 1
            self._http_peak_in_flight = max(self._http_peak_in_flight, self._http_in_flight)

    def request_finished(self, method: str, path: str, status_code: int, elapsed_ms: float) -> None:
        key = f"{method.upper()} {path}"
        with self._lock:
            self._http_in_flight = max(0, self._http_in_flight - 1)
            if key not in self._routes and len(self._routes) >= self._max_routes:
                key = "__other__"
            stats = self._routes.setdefault(
                key,
                {"count": 0, "errors": 0, "slow": 0, "total_ms": 0.0, "max_ms": 0.0},
            )
            stats["count"] += 1
            stats["errors"] += int(status_code >= 500)
            stats["slow"] += int(elapsed_ms >= self.slow_request_ms)
            stats["total_ms"] += elapsed_ms
            stats["max_ms"] = max(stats["max_ms"], elapsed_ms)
            stats["last_ms"] = round(elapsed_ms, 3)
            stats["last_status"] = int(status_code)
            if elapsed_ms >= self.slow_request_ms:
                self._recent_slow_requests.append(
                    {
                        "timestamp": _now_iso(),
                        "route": key,
                        "status": int(status_code),
                        "elapsed_ms": round(elapsed_ms, 3),
                    }
                )

    def http_admission_accepted(self, *, priority: bool) -> None:
        lane = "priority" if priority else "general"
        with self._lock:
            self._http_admission["active"] += 1
            self._http_admission[f"active_{lane}"] += 1
            self._http_admission["accepted"] += 1
            self._http_admission[f"accepted_{lane}"] += 1
            self._http_admission["peak_active"] = max(
                self._http_admission["peak_active"],
                self._http_admission["active"],
            )

    def http_admission_rejected(self, *, priority: bool) -> None:
        lane = "priority" if priority else "general"
        with self._lock:
            self._http_admission["rejected"] += 1
            self._http_admission[f"rejected_{lane}"] += 1

    def http_admission_released(self, *, priority: bool) -> None:
        lane = "priority" if priority else "general"
        with self._lock:
            self._http_admission["active"] = max(
                0, self._http_admission["active"] - 1
            )
            self._http_admission[f"active_{lane}"] = max(
                0, self._http_admission[f"active_{lane}"] - 1
            )

    def background_finished(self, name: str, elapsed_ms: float, *, error: bool = False, missed: int = 0) -> None:
        with self._lock:
            stats = self._background.setdefault(
                name,
                {"count": 0, "errors": 0, "missed_cycles": 0, "total_ms": 0.0, "max_ms": 0.0},
            )
            stats["count"] += 1
            stats["errors"] += int(error)
            stats["missed_cycles"] += max(0, int(missed))
            stats["total_ms"] += elapsed_ms
            stats["max_ms"] = max(stats["max_ms"], elapsed_ms)
            stats["last_ms"] = round(elapsed_ms, 3)
            stats["last_completed_at"] = _now_iso()

    def event_loop_sample(self, lag_ms: float, task_count: int) -> None:
        with self._lock:
            self._event_loop_lag_ms = max(0.0, lag_ms)
            self._event_loop_lag_peak_ms = max(self._event_loop_lag_peak_ms, lag_ms)
            self._asyncio_tasks = max(0, int(task_count))
            self._asyncio_tasks_peak = max(self._asyncio_tasks_peak, self._asyncio_tasks)

    def websocket_connected(self) -> None:
        with self._lock:
            self._websockets["active"] += 1
            self._websockets["accepted"] += 1
            self._websockets["peak_active"] = max(
                self._websockets["peak_active"], self._websockets["active"]
            )

    def websocket_rejected(self) -> None:
        with self._lock:
            self._websockets["rejected_clients"] += 1

    def websocket_send_timeout(self) -> None:
        with self._lock:
            self._websockets["send_timeouts"] += 1
            self._websockets["backpressure_disconnects"] += 1

    def websocket_disconnected(self, *, send_failure: bool = False) -> None:
        with self._lock:
            self._websockets["active"] = max(0, self._websockets["active"] - 1)
            self._websockets["disconnected"] += 1
            self._websockets["send_failures"] += int(send_failure)

    @staticmethod
    def _read_kib_fields(path: Path, wanted: set[str]) -> dict[str, int]:
        values: dict[str, int] = {}
        try:
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    parts = line.split()
                    if len(parts) >= 2 and parts[0].rstrip(":") in wanted:
                        values[parts[0].rstrip(":")] = int(parts[1]) * 1024
        except (OSError, ValueError, IndexError):
            pass
        return values

    @classmethod
    def _process_memory(cls) -> dict[str, Any]:
        rss_kib = None
        threads = threading.active_count()
        try:
            with open("/proc/self/status", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("VmRSS:"):
                        rss_kib = int(line.split()[1])
                    elif line.startswith("Threads:"):
                        threads = int(line.split()[1])
        except (OSError, ValueError, IndexError):
            pass
        rss_bytes = rss_kib * 1024 if rss_kib is not None else None
        peak_bytes = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024
        if rss_bytes is not None:
            peak_bytes = max(peak_bytes, rss_bytes)
        result = {
            "rss_bytes": rss_bytes,
            "peak_rss_bytes": peak_bytes,
            "threads": threads,
        }
        rollup = cls._read_kib_fields(
            Path("/proc/self/smaps_rollup"),
            {
                "Pss",
                "Pss_Anon",
                "Pss_File",
                "Pss_Shmem",
                "Private_Clean",
                "Private_Dirty",
                "Shared_Clean",
                "Shared_Dirty",
                "Swap",
            },
        )
        status = cls._read_kib_fields(
            Path("/proc/self/status"), {"RssAnon", "RssFile", "RssShmem", "VmSwap"}
        )
        result["breakdown"] = {
            "rss_anon_bytes": status.get("RssAnon"),
            "rss_file_bytes": status.get("RssFile"),
            "rss_shmem_bytes": status.get("RssShmem"),
            "pss_bytes": rollup.get("Pss"),
            "pss_anon_bytes": rollup.get("Pss_Anon"),
            "pss_file_bytes": rollup.get("Pss_File"),
            "pss_shmem_bytes": rollup.get("Pss_Shmem"),
            "private_clean_bytes": rollup.get("Private_Clean"),
            "private_dirty_bytes": rollup.get("Private_Dirty"),
            "shared_clean_bytes": rollup.get("Shared_Clean"),
            "shared_dirty_bytes": rollup.get("Shared_Dirty"),
            "swap_bytes": rollup.get("Swap", status.get("VmSwap")),
        }
        return result

    @staticmethod
    def _read_int(path: Path) -> int | None:
        try:
            return int(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None

    @staticmethod
    def _line_count(path: Path) -> int | None:
        try:
            return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        except OSError:
            return None

    @classmethod
    def _cgroup_memory(cls) -> dict[str, Any]:
        """Return a bounded cgroup-v2 view; never fail the diagnostics route."""
        result: dict[str, Any] = {"available": False, "version": None}
        try:
            cgroup_line = next(
                line for line in Path("/proc/self/cgroup").read_text(encoding="utf-8").splitlines()
                if line.startswith("0::")
            )
        except (OSError, StopIteration):
            return result

        relative = cgroup_line.partition("::")[2].lstrip("/")
        cgroup_path = Path("/sys/fs/cgroup") / relative
        if not (cgroup_path / "memory.current").is_file():
            return result

        result.update(
            {
                "available": True,
                "version": 2,
                "path": "/" + relative if relative else "/",
                "current_bytes": cls._read_int(cgroup_path / "memory.current"),
                "peak_bytes": cls._read_int(cgroup_path / "memory.peak"),
                "swap_current_bytes": cls._read_int(cgroup_path / "memory.swap.current"),
                "process_count": cls._line_count(cgroup_path / "cgroup.procs"),
                "thread_count": cls._line_count(cgroup_path / "cgroup.threads"),
                "pids_current": cls._read_int(cgroup_path / "pids.current"),
            }
        )

        wanted = {
            "anon",
            "file",
            "kernel",
            "kernel_stack",
            "pagetables",
            "percpu",
            "sock",
            "shmem",
            "file_mapped",
            "file_dirty",
            "file_writeback",
            "slab",
            "slab_reclaimable",
            "slab_unreclaimable",
        }
        breakdown: dict[str, int] = {}
        try:
            for line in (cgroup_path / "memory.stat").read_text(encoding="utf-8").splitlines():
                name, raw_value = line.split(maxsplit=1)
                if name in wanted:
                    breakdown[f"{name}_bytes"] = int(raw_value)
        except (OSError, ValueError):
            pass
        result["breakdown"] = breakdown

        events: dict[str, int] = {}
        try:
            for line in (cgroup_path / "memory.events").read_text(encoding="utf-8").splitlines():
                name, raw_value = line.split(maxsplit=1)
                if name in {"low", "high", "max", "oom", "oom_kill", "oom_group_kill"}:
                    events[name] = int(raw_value)
        except (OSError, ValueError):
            pass
        result["events"] = events
        return result

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            routes = deepcopy(self._routes)
            for stats in routes.values():
                stats["average_ms"] = round(stats["total_ms"] / stats["count"], 3)
                stats["total_ms"] = round(stats["total_ms"], 3)
                stats["max_ms"] = round(stats["max_ms"], 3)
            background = deepcopy(self._background)
            for stats in background.values():
                stats["average_ms"] = round(stats["total_ms"] / stats["count"], 3)
                stats["total_ms"] = round(stats["total_ms"], 3)
                stats["max_ms"] = round(stats["max_ms"], 3)
            result = {
                "timestamp": _now_iso(),
                "uptime_seconds": round(time.monotonic() - self._started_monotonic, 3),
                "process": self._process_memory(),
                "cgroup": self._cgroup_memory(),
                "http": {
                    "in_flight": self._http_in_flight,
                    "peak_in_flight": self._http_peak_in_flight,
                    "slow_request_ms": self.slow_request_ms,
                    "routes": routes,
                    "recent_slow_requests": list(self._recent_slow_requests),
                    "admission": deepcopy(self._http_admission),
                },
                "background": background,
                "websockets": deepcopy(self._websockets),
                "event_loop": {
                    "lag_ms": round(self._event_loop_lag_ms, 3),
                    "peak_lag_ms": round(self._event_loop_lag_peak_ms, 3),
                    "task_count": self._asyncio_tasks,
                    "peak_task_count": self._asyncio_tasks_peak,
                },
            }
        return result
