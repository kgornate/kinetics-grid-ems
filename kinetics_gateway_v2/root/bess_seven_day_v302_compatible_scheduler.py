#!/usr/bin/env python3
"""Lean sequential BESS scheduler for Kinetics Gateway V3.0.2.

Design goals:
- One backend request at a time. No ThreadPoolExecutor and no parallel writes.
- Pair-specific cached status reads; no repeated /status/all fan-out.
- SOC is read from the cached rack endpoint with a short TTL.
- Prepare pairs sequentially, then apply the requested power in one step.
- Use the field-proven automatic-start endpoint as a bounded fallback.
- On gateway loss during an active session, keep retrying and safe-stop as soon
  as the API becomes available; do not crash/restart in a tight loop.
- Stop every pair sequentially and verify the final electrical safe state.

This program never writes Modbus registers directly. All writes go through the
Kinetics backend control-sequence API.
"""

from __future__ import annotations

import argparse
import fcntl
import gc
import json
import os
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
SCHEDULER_BUILD = "v302-lean-sequential-20260803-r3-reviewed"
PAIR_IDS = ("pair_1", "pair_2", "pair_3", "pair_4")
PAIR_NUMBER = {pair_id: index for index, pair_id in enumerate(PAIR_IDS, start=1)}
PAIR_RACK = {pair_id: index for index, pair_id in enumerate(PAIR_IDS, start=1)}

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
API_USER = os.environ.get("API_USER", "internal")
API_PASS = os.environ.get("API_PASS", "Internal@123")

CHARGE_START_TIME = os.environ.get("CHARGE_START_TIME", "10:00")
CHARGE_STOP_TIME = os.environ.get("CHARGE_STOP_TIME", "13:30")
DISCHARGE_START_TIME = os.environ.get("DISCHARGE_START_TIME", "17:00")
DISCHARGE_STOP_TIME = os.environ.get("DISCHARGE_STOP_TIME", "19:00")
CHARGE_KW = float(os.environ.get("CHARGE_KW", "125.0"))
DISCHARGE_KW = float(os.environ.get("DISCHARGE_KW", "200.0"))
CHARGE_STOP_SOC = float(os.environ.get("CHARGE_STOP_SOC", "96.0"))
MIN_DISCHARGE_SOC = float(os.environ.get("MIN_DISCHARGE_SOC", "20.0"))
SITE_MAX_TOTAL_POWER_KW = float(os.environ.get("SITE_MAX_TOTAL_POWER_KW", "1000.0"))

PREPARE_LEAD_MINUTES = int(os.environ.get("PREPARE_LEAD_MINUTES", "40"))
PREPARE_RETRY_ATTEMPTS = int(os.environ.get("PREPARE_RETRY_ATTEMPTS", "1"))
PCS_START_MAX_ATTEMPTS = int(os.environ.get("PCS_START_MAX_ATTEMPTS", "2"))
PCS_READY_TIMEOUT_SECONDS = int(os.environ.get("PCS_READY_TIMEOUT_SECONDS", "210"))
BMS_PRECHARGE_TIMEOUT_SECONDS = int(os.environ.get("BMS_PRECHARGE_TIMEOUT_SECONDS", "150"))
POWER_TRACK_TIMEOUT_SECONDS = int(os.environ.get("POWER_TRACK_TIMEOUT_SECONDS", "180"))
POWER_TRACK_MIN_FRACTION = float(os.environ.get("POWER_TRACK_MIN_FRACTION", "0.75"))
SETPOINT_TOLERANCE_KW = float(os.environ.get("SETPOINT_TOLERANCE_KW", "5.0"))
POWER_TRACK_MAX_FRACTION = float(os.environ.get("POWER_TRACK_MAX_FRACTION", "1.25"))
MONITOR_CYCLE_SECONDS = float(os.environ.get("MONITOR_CYCLE_SECONDS", "30"))
SOC_REFRESH_SECONDS = float(os.environ.get("SOC_REFRESH_SECONDS", "30"))
SOC_MAX_STALE_SECONDS = float(os.environ.get("SOC_MAX_STALE_SECONDS", "90"))
SOC_ERROR_LIMIT = int(os.environ.get("SOC_ERROR_LIMIT", "3"))
PAIR_STATUS_POLL_SECONDS = float(os.environ.get("PAIR_STATUS_POLL_SECONDS", "5"))
PAIR_COMMAND_SPACING_SECONDS = float(os.environ.get("PAIR_COMMAND_SPACING_SECONDS", "3"))
MIN_START_REMAINING_SECONDS = int(os.environ.get("MIN_START_REMAINING_SECONDS", "900"))
MEMORY_LOG_INTERVAL_SECONDS = float(os.environ.get("MEMORY_LOG_INTERVAL_SECONDS", "300"))
STATUS_ERROR_LIMIT = int(os.environ.get("STATUS_ERROR_LIMIT", "3"))
POWER_VIOLATION_LIMIT = int(os.environ.get("POWER_VIOLATION_LIMIT", "2"))
GATEWAY_RETRY_SECONDS = float(os.environ.get("GATEWAY_RETRY_SECONDS", "5"))
GATEWAY_ACTIVE_OUTAGE_LIMIT_SECONDS = int(
    os.environ.get("GATEWAY_ACTIVE_OUTAGE_LIMIT_SECONDS", "20")
)
EXIT_SAFE_STOP_RECOVERY_SECONDS = int(
    os.environ.get("EXIT_SAFE_STOP_RECOVERY_SECONDS", "300")
)
SAFE_STOP_NOW_GATEWAY_WAIT_SECONDS = int(
    os.environ.get("SAFE_STOP_NOW_GATEWAY_WAIT_SECONDS", "300")
)
MAX_API_BODY_BYTES = int(os.environ.get("MAX_API_BODY_BYTES", str(2 * 1024 * 1024)))

STAGE_CONFIRMATION = os.environ.get("STAGE_CONFIRMATION", "EXECUTE_STAGE_WRITE")
AUTOMATIC_CONFIRMATION = os.environ.get(
    "AUTOMATIC_CONFIRMATION", "EXECUTE_AUTOMATIC_SEQUENCE"
)
ARM_PHRASE = os.environ.get("ARM_PHRASE", "")
REQUIRED_ARM_PHRASE = "EXECUTE_7_DAY_BACKEND_V3_SCHEDULE"

STATE_DIR = Path(
    os.environ.get("STATE_DIR", "/mnt/ems-logs/scheduler/bess-seven-day-v302")
)
STATE_FILE = STATE_DIR / "state.json"
LOCK_FILE = Path(os.environ.get("LOCK_FILE", "/run/bess-seven-day-v302.lock"))
ROOT_MIN_FREE_MB = int(os.environ.get("ROOT_MIN_FREE_MB", "512"))

STOP_REQUESTED = threading.Event()
LOG_LOCK = threading.Lock()
STATE_LOCK = threading.Lock()
TOKEN_LOCK = threading.Lock()
TOKEN: str | None = None
LOCK_HANDLE: Any = None
HARDWARE_MAY_BE_ACTIVE = False


class OperatorStop(Exception):
    pass


class GatewayUnavailable(RuntimeError):
    pass


class SessionAborted(RuntimeError):
    pass


@dataclass(frozen=True)
class SessionTimes:
    prepare: datetime
    start: datetime
    stop: datetime


@dataclass
class PairStatus:
    pair_id: str
    soc: float | None
    precharge_state: int
    positive_contactor_closed: bool
    negative_contactor_closed: bool
    pcs_state: int
    set_kw: float
    actual_kw: float
    charge_limit_a: float
    discharge_limit_a: float
    fault: bool
    ready_for_power: bool
    errors: list[Any]
    runtime_status: str | None
    runtime_stage: str | None
    raw_summary: dict[str, Any]


def log(message: str) -> None:
    stamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S %Z")
    with LOG_LOCK:
        print(f"[{stamp}] {message}", flush=True)


def signal_handler(signum: int, _frame: Any) -> None:
    STOP_REQUESTED.set()
    log(f"Signal {signum} received; sequential safe-stop requested")


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def check_stop() -> None:
    if STOP_REQUESTED.is_set():
        raise OperatorStop("operator stop requested")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_hhmm(value: str):
    return datetime.strptime(value, "%H:%M").time()


def at_ist(day: date, hhmm: str) -> datetime:
    return datetime.combine(day, parse_hhmm(hhmm), tzinfo=IST)


def session_times(day: date, direction: str) -> SessionTimes:
    if direction == "charge":
        start = at_ist(day, CHARGE_START_TIME)
        stop = at_ist(day, CHARGE_STOP_TIME)
    elif direction == "discharge":
        start = at_ist(day, DISCHARGE_START_TIME)
        stop = at_ist(day, DISCHARGE_STOP_TIME)
    else:
        raise ValueError(direction)
    return SessionTimes(
        prepare=start - timedelta(minutes=PREPARE_LEAD_MINUTES),
        start=start,
        stop=stop,
    )


def schedule_dates() -> list[date]:
    explicit = os.environ.get("SCHEDULE_DATES", "").strip()
    if explicit:
        return sorted(
            {
                date.fromisoformat(item.strip())
                for item in explicit.split(",")
                if item.strip()
            }
        )
    start_text = os.environ.get("SCHEDULE_START_DATE", "").strip()
    start_day = (
        date.fromisoformat(start_text)
        if start_text
        else datetime.now(IST).date() + timedelta(days=1)
    )
    count = int(os.environ.get("SCHEDULE_DAYS", "7"))
    return [start_day + timedelta(days=index) for index in range(count)]


SCHEDULE_DATES = schedule_dates()


def session_key(day: date, direction: str) -> str:
    return f"{day.isoformat()}:{direction}"


def root_free_mb() -> float:
    stat = os.statvfs("/")
    return stat.f_bavail * stat.f_frsize / (1024 * 1024)


def validate_configuration() -> None:
    if ARM_PHRASE != REQUIRED_ARM_PHRASE:
        raise RuntimeError("scheduler ARM_PHRASE is missing or incorrect")
    if not SCHEDULE_DATES:
        raise RuntimeError("no schedule dates configured")
    if CHARGE_KW <= 0 or DISCHARGE_KW <= 0:
        raise RuntimeError("charge/discharge kW must be positive")
    if max(CHARGE_KW, DISCHARGE_KW) * len(PAIR_IDS) > SITE_MAX_TOTAL_POWER_KW:
        raise RuntimeError("requested total pair power exceeds site limit")
    if not 0 < MIN_DISCHARGE_SOC < CHARGE_STOP_SOC <= 100:
        raise RuntimeError("invalid SOC cutoffs")
    if PREPARE_LEAD_MINUTES < 5:
        raise RuntimeError("PREPARE_LEAD_MINUTES must be at least 5")
    if not 1 <= PCS_START_MAX_ATTEMPTS <= 3:
        raise RuntimeError("PCS_START_MAX_ATTEMPTS must be 1..3")
    if not 0 <= PREPARE_RETRY_ATTEMPTS <= 2:
        raise RuntimeError("PREPARE_RETRY_ATTEMPTS must be 0..2")
    if not 10 <= MONITOR_CYCLE_SECONDS <= 120:
        raise RuntimeError("MONITOR_CYCLE_SECONDS must be 10..120")
    if not 2 <= PAIR_STATUS_POLL_SECONDS <= 15:
        raise RuntimeError("PAIR_STATUS_POLL_SECONDS must be 2..15")
    if not 0 <= PAIR_COMMAND_SPACING_SECONDS <= 15:
        raise RuntimeError("PAIR_COMMAND_SPACING_SECONDS must be 0..15")
    if not 10 <= SOC_REFRESH_SECONDS <= 120:
        raise RuntimeError("SOC_REFRESH_SECONDS must be 10..120")
    if not 0.5 <= POWER_TRACK_MIN_FRACTION <= 1.0:
        raise RuntimeError("invalid POWER_TRACK_MIN_FRACTION")
    if not 1.0 <= POWER_TRACK_MAX_FRACTION <= 2.0:
        raise RuntimeError("invalid POWER_TRACK_MAX_FRACTION")
    if not 0.5 <= SETPOINT_TOLERANCE_KW <= 25.0:
        raise RuntimeError("invalid SETPOINT_TOLERANCE_KW")
    if not SOC_REFRESH_SECONDS <= SOC_MAX_STALE_SECONDS <= 600:
        raise RuntimeError("SOC_MAX_STALE_SECONDS must be >= refresh interval and <= 600")
    if not 1 <= SOC_ERROR_LIMIT <= 10:
        raise RuntimeError("SOC_ERROR_LIMIT must be 1..10")
    if not 60 <= MIN_START_REMAINING_SECONDS <= 3600:
        raise RuntimeError("MIN_START_REMAINING_SECONDS must be 60..3600")
    if root_free_mb() < ROOT_MIN_FREE_MB:
        raise RuntimeError(
            f"root filesystem has only {root_free_mb():.1f} MB free; "
            f"minimum is {ROOT_MIN_FREE_MB} MB"
        )
    for day in SCHEDULE_DATES:
        for direction in ("charge", "discharge"):
            times = session_times(day, direction)
            if not times.prepare < times.start < times.stop:
                raise RuntimeError(f"invalid {direction} times for {day}")
    log(
        "Configuration valid: "
        f"dates={[d.isoformat() for d in SCHEDULE_DATES]}, "
        f"charge={CHARGE_START_TIME}-{CHARGE_STOP_TIME} at {CHARGE_KW:.1f} kW/pair, "
        f"discharge={DISCHARGE_START_TIME}-{DISCHARGE_STOP_TIME} at "
        f"{DISCHARGE_KW:.1f} kW/pair, sequential_io=true, "
        f"monitor_cycle={MONITOR_CYCLE_SECONDS:.0f}s, "
        f"soc_refresh={SOC_REFRESH_SECONDS:.0f}s"
    )


def acquire_lock() -> None:
    global LOCK_HANDLE
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_HANDLE = LOCK_FILE.open("w", encoding="utf-8")
    try:
        fcntl.flock(LOCK_HANDLE.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        raise RuntimeError("another scheduler instance is already running") from error
    LOCK_HANDLE.write(str(os.getpid()))
    LOCK_HANDLE.flush()


def default_state() -> dict[str, Any]:
    return {
        "version": 5,
        "build": SCHEDULER_BUILD,
        "schedule_dates": [day.isoformat() for day in SCHEDULE_DATES],
        "phase": "waiting",
        "current_date": None,
        "current_session": None,
        "prepared_pairs": [],
        "active_pairs": [],
        "completed_sessions": [],
        "last_update": datetime.now(IST).isoformat(),
    }


def load_state() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        state = default_state()
        save_state(state)
        return state
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception as error:
        backup = STATE_FILE.with_name(
            f"state.corrupt.{datetime.now(IST).strftime('%Y%m%d_%H%M%S')}.json"
        )
        STATE_FILE.replace(backup)
        log(f"Corrupt state moved to {backup}: {error}")
        state = default_state()
    state["version"] = 5
    state["build"] = SCHEDULER_BUILD
    state["schedule_dates"] = [day.isoformat() for day in SCHEDULE_DATES]
    state.setdefault("completed_sessions", [])
    return state


def save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state["last_update"] = datetime.now(IST).isoformat()
    temporary = STATE_FILE.with_suffix(".tmp")
    with STATE_LOCK:
        temporary.write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, STATE_FILE)


def update_state(
    state: dict[str, Any],
    *,
    phase: str,
    day: date | None = None,
    direction: str | None = None,
    prepared: set[str] | None = None,
    active: set[str] | None = None,
) -> None:
    state["phase"] = phase
    state["current_date"] = day.isoformat() if day else None
    state["current_session"] = direction
    state["prepared_pairs"] = sorted(prepared or set())
    state["active_pairs"] = sorted(active or set())
    save_state(state)


def mark_complete(state: dict[str, Any], day: date, direction: str) -> None:
    completed = set(state.get("completed_sessions") or [])
    completed.add(session_key(day, direction))
    state["completed_sessions"] = sorted(completed)
    update_state(state, phase="waiting")


class ApiClient:
    def __init__(self) -> None:
        self._soc_cache: dict[int, float] = {}
        self._soc_cache_time: float = 0.0

    def _set_token(self, value: str | None) -> None:
        global TOKEN
        with TOKEN_LOCK:
            TOKEN = value

    def _get_token(self) -> str | None:
        with TOKEN_LOCK:
            return TOKEN

    def login(self) -> None:
        payload = json.dumps({"username": API_USER, "password": API_PASS}).encode()
        request = urllib.request.Request(
            f"{BASE_URL}/api/auth/login",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json", "Connection": "close"},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read(MAX_API_BODY_BYTES + 1)
        except Exception as error:
            raise GatewayUnavailable(f"gateway login failed: {error}") from error
        if len(body) > MAX_API_BODY_BYTES:
            raise RuntimeError("gateway login response exceeded size limit")
        result = json.loads(body.decode())
        token = result.get("access_token")
        if not token:
            raise RuntimeError("login response did not include access_token")
        self._set_token(str(token))
        log(f"Gateway authentication successful as {result.get('username', API_USER)}")

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float = 30,
        attempts: int = 2,
        authenticate: bool = True,
        retry_transport: bool = True,
    ) -> dict[str, Any]:
        if authenticate and self._get_token() is None:
            self.login()
        data = None if payload is None else json.dumps(payload).encode()
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Connection": "close",
            }
            if authenticate:
                headers["Authorization"] = f"Bearer {self._get_token()}"
            request = urllib.request.Request(
                f"{BASE_URL}{path}", data=data, method=method, headers=headers
            )
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    body = response.read(MAX_API_BODY_BYTES + 1)
                if len(body) > MAX_API_BODY_BYTES:
                    raise RuntimeError(f"API response too large for {path}")
                return json.loads(body.decode()) if body else {}
            except urllib.error.HTTPError as error:
                detail = error.read(32768).decode(errors="replace")
                if error.code == 401 and authenticate and attempt == 1:
                    self._set_token(None)
                    self.login()
                    continue
                if error.code >= 500 or error.code == 429:
                    last_error = GatewayUnavailable(
                        f"gateway HTTP {error.code} {method} {path}: {detail}"
                    )
                else:
                    last_error = RuntimeError(f"HTTP {error.code} {path}: {detail}")
                    if error.code in {400, 403, 404, 409, 422}:
                        raise last_error from error
            except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
                last_error = GatewayUnavailable(
                    f"API request failed {method} {path}: {error}"
                )
            except json.JSONDecodeError as error:
                last_error = RuntimeError(f"invalid JSON from {path}: {error}")
            if not retry_transport and last_error is not None:
                raise last_error
            if attempt < attempts:
                STOP_REQUESTED.wait(1.0)
        assert last_error is not None
        raise last_error

    def health(self) -> dict[str, Any]:
        return self.request(
            "GET", "/api/health", timeout=10, attempts=1, authenticate=False
        )

    def wait_available(self, reason: str, timeout: float | None = None) -> bool:
        deadline = None if timeout is None else time.monotonic() + timeout
        logged = False
        while deadline is None or time.monotonic() < deadline:
            try:
                health = self.health()
                self._set_token(None)
                self.login()
                log(
                    f"Gateway API recovered for {reason}; "
                    f"health={health.get('status', 'unknown')}"
                )
                return True
            except Exception as error:
                if not logged:
                    log(f"Gateway unavailable during {reason}: {error}")
                    logged = True
                # Do not use Event.wait here: after SIGTERM the event is set and
                # would create a tight CPU loop while the gateway is unavailable.
                time.sleep(GATEWAY_RETRY_SECONDS)
        return False

    def capabilities(self) -> dict[str, Any]:
        return self.request("GET", "/api/control-sequence/capabilities", timeout=30)

    @staticmethod
    def _point_value(point: Any) -> Any:
        if isinstance(point, dict):
            if "value" in point:
                return point.get("value")
            return point.get("v")
        return point

    def _refresh_soc_cache(self) -> None:
        """Refresh all four SOC values with one lightweight cached-snapshot call."""
        result = self.request("GET", "/api/bms/racks", timeout=20, attempts=2)
        racks = result.get("racks") or []
        values: dict[int, float] = {}
        for rack in racks:
            try:
                rack_id = int(rack.get("rack_id"))
            except (TypeError, ValueError):
                continue
            if not rack.get("online", False):
                continue
            point = (rack.get("telemetry") or {}).get("soc")
            if not isinstance(point, dict):
                continue
            quality = str(point.get("quality", point.get("q", "unknown"))).lower()
            if quality not in {"good", "ok"}:
                continue
            raw = self._point_value(point)
            if raw is None:
                continue
            value = float(raw)
            if "‰" in str(point.get("unit") or "") or value > 100.0:
                value /= 10.0
            if 0 <= value <= 100:
                values[rack_id] = value
        if not values:
            raise RuntimeError("BMS rack SOC snapshot is unavailable")
        self._soc_cache = values
        self._soc_cache_time = time.monotonic()

    def refresh_soc_snapshot(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if force or not self._soc_cache or now - self._soc_cache_time > SOC_REFRESH_SECONDS:
            self._refresh_soc_cache()

    def soc(
        self,
        rack_id: int,
        *,
        force: bool = False,
        allow_refresh: bool = True,
    ) -> float:
        now = time.monotonic()
        if allow_refresh and (
            force
            or rack_id not in self._soc_cache
            or now - self._soc_cache_time > SOC_REFRESH_SECONDS
        ):
            self._refresh_soc_cache()
            now = time.monotonic()
        age = now - self._soc_cache_time
        if rack_id not in self._soc_cache:
            raise RuntimeError(f"BMS rack {rack_id} SOC is unavailable")
        if age > SOC_MAX_STALE_SECONDS:
            raise RuntimeError(
                f"BMS SOC snapshot is stale ({age:.1f}s > {SOC_MAX_STALE_SECONDS:.1f}s)"
            )
        return self._soc_cache[rack_id]

    def pair_status(
        self,
        pair_id: str,
        *,
        fresh: bool = False,
        include_soc: bool = True,
        force_soc: bool = False,
        allow_soc_refresh: bool = True,
    ) -> PairStatus:
        status = self.request(
            "GET",
            f"/api/control-sequence/{pair_id}/status?fresh={'true' if fresh else 'false'}",
            timeout=30 if not fresh else 60,
            attempts=2,
        )
        summary = dict(status.get("summary") or {})
        workflow = status.get("workflow") or {}
        runtime = status.get("runtime") or {}
        blockers = summary.get("blockers") or {}
        fault = any(
            (
                bool(summary.get("pcs_fault_shutdown")),
                bool(blockers.get("system_fault")),
                bool(blockers.get("documented_critical_fault")),
                bool(blockers.get("emergency_stop_fault")),
            )
        )
        soc = None
        if include_soc:
            soc = self.soc(
                PAIR_RACK[pair_id],
                force=force_soc,
                allow_refresh=allow_soc_refresh,
            )
        return PairStatus(
            pair_id=pair_id,
            soc=soc,
            precharge_state=int(float(summary.get("precharge_state") or 0)),
            positive_contactor_closed=bool(
                summary.get("positive_contactor_closed")
            ),
            negative_contactor_closed=bool(
                summary.get("negative_contactor_closed")
            ),
            pcs_state=int(float(summary.get("pcs_operating_state") or 0)),
            set_kw=float(summary.get("pcs_power_setpoint_kw") or 0.0),
            actual_kw=float(summary.get("pcs_actual_power_kw") or 0.0),
            charge_limit_a=float(summary.get("rack_charge_current_limit_a") or 0.0),
            discharge_limit_a=float(
                summary.get("rack_discharge_current_limit_a") or 0.0
            ),
            fault=fault,
            ready_for_power=bool(workflow.get("ready_for_power")),
            errors=list(status.get("errors") or []),
            runtime_status=runtime.get("run_status"),
            runtime_stage=runtime.get("stage"),
            raw_summary=summary,
        )


CLIENT = ApiClient()


def print_status(item: PairStatus) -> None:
    soc = "?" if item.soc is None else f"{item.soc:.1f}%"
    log(
        f"P{PAIR_NUMBER[item.pair_id]}: SOC={soc} PRE={item.precharge_state} "
        f"CONTACTORS={item.positive_contactor_closed}/"
        f"{item.negative_contactor_closed} PCS={item.pcs_state} "
        f"SET={item.set_kw:.1f} kW ACT={item.actual_kw:.1f} kW "
        f"CHG_LIMIT={item.charge_limit_a:.1f} A "
        f"DSG_LIMIT={item.discharge_limit_a:.1f} A FAULT={item.fault}"
    )


def power_zero(item: PairStatus) -> bool:
    return abs(item.set_kw) <= 0.5 and abs(item.actual_kw) <= 1.0


def fully_stopped(item: PairStatus) -> bool:
    return (
        item.precharge_state == 0
        and not item.positive_contactor_closed
        and not item.negative_contactor_closed
        and item.pcs_state == 1
        and power_zero(item)
    )


def bms_connected(item: PairStatus) -> bool:
    return (
        item.precharge_state == 3
        and item.positive_contactor_closed
        and item.negative_contactor_closed
        and not item.fault
    )


def direction_allowed(item: PairStatus, direction: str) -> bool:
    if direction == "charge":
        return item.charge_limit_a > 0
    return item.discharge_limit_a > 0


def ready_zero(item: PairStatus, direction: str) -> bool:
    return (
        item.pcs_state in {16, 80}
        and bms_connected(item)
        and direction_allowed(item, direction)
        and power_zero(item)
        and not item.errors
        and (item.ready_for_power or item.pcs_state == 16)
    )


def target_tracking(item: PairStatus, direction: str, target_kw: float) -> bool:
    expected_setpoint = -target_kw if direction == "charge" else target_kw
    setpoint_ok = abs(item.set_kw - expected_setpoint) <= SETPOINT_TOLERANCE_KW
    magnitude = abs(item.actual_kw)
    magnitude_ok = (
        target_kw * POWER_TRACK_MIN_FRACTION
        <= magnitude
        <= target_kw * POWER_TRACK_MAX_FRACTION
    )
    direction_ok = item.actual_kw < 0 if direction == "charge" else item.actual_kw > 0
    return setpoint_ok and magnitude_ok and direction_ok


def soc_allows(item: PairStatus, direction: str) -> bool:
    if item.soc is None:
        return False
    if direction == "charge":
        return item.soc < CHARGE_STOP_SOC
    return item.soc > MIN_DISCHARGE_SOC


def post_pair(
    pair_id: str,
    endpoint: str,
    extra: dict[str, Any] | None = None,
    *,
    timeout: float = 300,
) -> dict[str, Any]:
    body: dict[str, Any] = {"confirmation": STAGE_CONFIRMATION}
    if extra:
        body.update(extra)
    return CLIENT.request(
        "POST",
        f"/api/control-sequence/{pair_id}/{endpoint}",
        body,
        timeout=timeout,
        attempts=2,
        retry_transport=False,
    )


def wait_pair(
    pair_id: str,
    predicate: Callable[[PairStatus], bool],
    description: str,
    timeout_seconds: float,
    *,
    include_soc: bool = False,
    honor_stop: bool = True,
) -> PairStatus:
    deadline = time.monotonic() + timeout_seconds
    last: PairStatus | None = None
    last_error: Exception | None = None
    next_log = 0.0
    while time.monotonic() < deadline:
        if honor_stop:
            check_stop()
        try:
            last = CLIENT.pair_status(pair_id, include_soc=include_soc)
            last_error = None
            if time.monotonic() >= next_log:
                print_status(last)
                next_log = time.monotonic() + 20
            if predicate(last):
                log(f"P{PAIR_NUMBER[pair_id]}: verified {description}")
                return last
        except GatewayUnavailable:
            raise
        except Exception as error:
            last_error = error
            log(f"P{PAIR_NUMBER[pair_id]}: waiting for {description}: {error}")
        if honor_stop:
            STOP_REQUESTED.wait(PAIR_STATUS_POLL_SECONDS)
        else:
            time.sleep(PAIR_STATUS_POLL_SECONDS)
    detail = f"; last_error={last_error}" if last_error else ""
    if last is not None:
        detail += (
            f"; last_state=PRE{last.precharge_state}/PCS{last.pcs_state}/"
            f"SET{last.set_kw:.1f}/ACT{last.actual_kw:.1f}"
        )
    raise TimeoutError(f"timed out waiting for {description}{detail}")


def safe_stop_pair(pair_id: str, reason: str) -> bool:
    global HARDWARE_MAY_BE_ACTIVE
    HARDWARE_MAY_BE_ACTIVE = True
    log(f"P{PAIR_NUMBER[pair_id]}: sequential safe-stop starting ({reason})")
    try:
        response = post_pair(
            pair_id, "safe-stop", {"open_bms": True}, timeout=420
        )
        if response.get("ok") is False:
            raise RuntimeError(json.dumps(response.get("errors") or response))
        final = wait_pair(
            pair_id,
            fully_stopped,
            "zero power, PCS stopped and BMS contactors open",
            150,
            honor_stop=False,
        )
        print_status(final)
        log(f"P{PAIR_NUMBER[pair_id]}: safe-stop verified")
        return True
    except GatewayUnavailable:
        raise
    except Exception as error:
        log(f"P{PAIR_NUMBER[pair_id]}: safe-stop failed: {error}")
        return False


def safe_stop_all_sequential(reason: str) -> bool:
    global HARDWARE_MAY_BE_ACTIVE
    HARDWARE_MAY_BE_ACTIVE = True
    log(f"All-pair sequential shutdown starting: {reason}")
    failures: list[str] = []

    # First remove power from each pair. This is intentionally sequential so the
    # shared gateway/RTU lane never receives a burst of four write workflows.
    for pair_id in PAIR_IDS:
        try:
            item = CLIENT.pair_status(pair_id, include_soc=False)
            if abs(item.set_kw) > 0.5 or abs(item.actual_kw) > 1.0:
                log(f"P{PAIR_NUMBER[pair_id]}: zero-power request")
                response = post_pair(pair_id, "zero-power", timeout=240)
                if response.get("ok") is False:
                    log(f"P{PAIR_NUMBER[pair_id]}: zero-power response not OK")
        except GatewayUnavailable:
            raise
        except Exception as error:
            log(f"P{PAIR_NUMBER[pair_id]}: zero-power warning: {error}")
        time.sleep(PAIR_COMMAND_SPACING_SECONDS)

    for pair_id in PAIR_IDS:
        try:
            item = CLIENT.pair_status(pair_id, include_soc=False)
            if fully_stopped(item):
                log(f"P{PAIR_NUMBER[pair_id]}: already safely stopped")
                continue
        except GatewayUnavailable:
            raise
        except Exception as error:
            log(f"P{PAIR_NUMBER[pair_id]}: pre-stop status warning: {error}")
        if not safe_stop_pair(pair_id, reason):
            failures.append(pair_id)
        time.sleep(PAIR_COMMAND_SPACING_SECONDS)

    final_failures: list[str] = []
    for pair_id in PAIR_IDS:
        try:
            item = CLIENT.pair_status(
                pair_id, fresh=True, include_soc=False
            )
            print_status(item)
            if not fully_stopped(item):
                final_failures.append(pair_id)
        except Exception as error:
            log(f"P{PAIR_NUMBER[pair_id]}: final verification failed: {error}")
            final_failures.append(pair_id)

    # The fresh electrical verification is authoritative. A control endpoint may
    # time out after the hardware already reached the stopped state; do not turn
    # that recovered condition into a false shutdown failure.
    if failures and not final_failures:
        log(f"Transient stop-command errors recovered by fresh verification: {failures}")
    unresolved = sorted(set(final_failures))
    if unresolved:
        log(f"CRITICAL: safe shutdown remains unverified for {unresolved}")
        return False
    HARDWARE_MAY_BE_ACTIVE = False
    log("All four pairs verified at zero power, PCS stopped and contactors open")
    return True


def recover_gateway_and_safe_stop(reason: str, timeout: float | None = None) -> bool:
    log(f"Fail-safe pending because gateway is unavailable: {reason}")
    if not CLIENT.wait_available(reason, timeout=timeout):
        log("CRITICAL: gateway did not recover before fail-safe timeout")
        return False
    try:
        return safe_stop_all_sequential(f"gateway recovery: {reason}")
    except GatewayUnavailable as error:
        log(f"Gateway failed again during recovered safe-stop: {error}")
        return False


def prepare_pair(pair_id: str, direction: str) -> bool:
    total_cycles = 1 + PREPARE_RETRY_ATTEMPTS
    for cycle in range(1, total_cycles + 1):
        check_stop()
        try:
            item = CLIENT.pair_status(pair_id, include_soc=True)
            print_status(item)
            if item.fault or item.errors:
                log(
                    f"P{PAIR_NUMBER[pair_id]}: excluded from {direction}; "
                    "fault or control-status errors are present"
                )
                if not fully_stopped(item):
                    safe_stop_pair(pair_id, f"fault/error before {direction} preparation")
                return False
            if not soc_allows(item, direction):
                log(
                    f"P{PAIR_NUMBER[pair_id]}: excluded from {direction}; "
                    f"SOC={item.soc}"
                )
                return False
            if ready_zero(item, direction):
                log(f"P{PAIR_NUMBER[pair_id]}: already ready at zero power")
                return True
            if not fully_stopped(item):
                if not safe_stop_pair(pair_id, f"baseline before {direction} preparation"):
                    raise RuntimeError("baseline safe-stop could not be verified")

            log(
                f"P{PAIR_NUMBER[pair_id]}: configuring PCS at zero power "
                f"(cycle {cycle}/{total_cycles})"
            )
            response = post_pair(pair_id, "configure-pcs", timeout=240)
            if response.get("ok") is False:
                raise RuntimeError("configure-pcs returned unsuccessful")

            log(f"P{PAIR_NUMBER[pair_id]}: requesting BAU precharge")
            response = post_pair(pair_id, "start-precharge", timeout=240)
            if response.get("ok") is False:
                raise RuntimeError("start-precharge returned unsuccessful")

            wait_pair(
                pair_id,
                bms_connected,
                "BMS precharge state 3 and both contactors closed",
                BMS_PRECHARGE_TIMEOUT_SECONDS,
            )

            last_error: Exception | None = None
            for attempt in range(1, PCS_START_MAX_ATTEMPTS + 1):
                check_stop()
                current = CLIENT.pair_status(pair_id, include_soc=False)
                if ready_zero(current, direction):
                    log(f"P{PAIR_NUMBER[pair_id]}: PCS already ready at zero power")
                    return True
                if not bms_connected(current) or current.fault or not power_zero(current):
                    raise RuntimeError(
                        "PCS start blocked by BMS/fault/nonzero-power state"
                    )
                log(
                    f"P{PAIR_NUMBER[pair_id]}: starting PCS at zero power "
                    f"(attempt {attempt}/{PCS_START_MAX_ATTEMPTS})"
                )
                try:
                    response = post_pair(pair_id, "start-pcs", timeout=360)
                    if response.get("ok") is False:
                        raise RuntimeError("start-pcs returned unsuccessful")
                    wait_pair(
                        pair_id,
                        lambda value: ready_zero(value, direction),
                        f"PCS/BMS ready at zero power for {direction}",
                        PCS_READY_TIMEOUT_SECONDS,
                    )
                    log(f"P{PAIR_NUMBER[pair_id]}: {direction} preparation complete")
                    return True
                except GatewayUnavailable:
                    raise
                except Exception as error:
                    last_error = error
                    latest = CLIENT.pair_status(pair_id, include_soc=False)
                    print_status(latest)
                    can_retry = (
                        attempt < PCS_START_MAX_ATTEMPTS
                        and latest.pcs_state == 1
                        and bms_connected(latest)
                        and power_zero(latest)
                        and not latest.fault
                    )
                    log(
                        f"P{PAIR_NUMBER[pair_id]}: PCS readiness attempt {attempt} "
                        f"failed; can_retry={can_retry}; error={error}"
                    )
                    if not can_retry:
                        raise RuntimeError(
                            f"PCS did not become ready: {error}"
                        ) from error
                    STOP_REQUESTED.wait(5)
            raise RuntimeError(f"PCS start attempts exhausted: {last_error}")
        except OperatorStop:
            safe_stop_pair(pair_id, "operator stop during preparation")
            raise
        except GatewayUnavailable:
            raise
        except Exception as error:
            log(
                f"P{PAIR_NUMBER[pair_id]}: {direction} preparation cycle "
                f"{cycle} failed: {error}"
            )
            if not safe_stop_pair(pair_id, f"{direction} preparation failure"):
                raise RuntimeError(
                    f"preparation failed and safe-stop is unverified: {error}"
                ) from error
            if cycle < total_cycles:
                log(f"P{PAIR_NUMBER[pair_id]}: retrying full preparation in 10s")
                STOP_REQUESTED.wait(10)
                continue
            return False
    return False


def automatic_start_direct(pair_id: str, direction: str, target_kw: float) -> bool:
    log(
        f"P{PAIR_NUMBER[pair_id]}: field-proven direct automatic-start "
        f"at {target_kw:.1f} kW (single power step)"
    )
    response = CLIENT.request(
        "POST",
        f"/api/control-sequence/{pair_id}/automatic-start",
        {
            "direction": direction,
            "power_kw": target_kw,
            "ramp_step_kw": target_kw,
            "ramp_interval_seconds": 1,
            "confirmation": AUTOMATIC_CONFIRMATION,
        },
        timeout=60,
        attempts=2,
        retry_transport=False,
    )
    if response.get("ok") is False:
        raise RuntimeError("automatic-start returned unsuccessful")
    wait_pair(
        pair_id,
        lambda value: target_tracking(value, direction, target_kw),
        f"direct {direction} target tracking",
        420,
    )
    return True


def start_power_pair(pair_id: str, direction: str, target_kw: float) -> bool:
    global HARDWARE_MAY_BE_ACTIVE
    check_stop()
    item = CLIENT.pair_status(pair_id, include_soc=True)
    print_status(item)
    if item.fault or item.errors:
        log(f"P{PAIR_NUMBER[pair_id]}: fault/status errors block {direction} start")
        if not fully_stopped(item):
            safe_stop_pair(pair_id, f"fault/error before {direction} start")
        return False
    if not soc_allows(item, direction):
        log(f"P{PAIR_NUMBER[pair_id]}: SOC cutoff blocks {direction} start")
        if not fully_stopped(item):
            safe_stop_pair(pair_id, "SOC cutoff before start")
        return False
    if target_tracking(item, direction, target_kw):
        log(f"P{PAIR_NUMBER[pair_id]}: target already active; adopting pair")
        HARDWARE_MAY_BE_ACTIVE = True
        return True

    # Normal path: pair was prepared early. Apply the target directly, with one
    # bounded retry if pcs_ready_state changes momentarily.
    if ready_zero(item, direction):
        last_error: Exception | None = None
        for attempt in (1, 2):
            try:
                HARDWARE_MAY_BE_ACTIVE = True
                response = post_pair(
                    pair_id,
                    "set-power",
                    {"direction": direction, "power_kw": target_kw},
                    timeout=300,
                )
                if response.get("ok") is False:
                    raise RuntimeError("set-power returned unsuccessful")
                sign = "-" if direction == "charge" else "+"
                log(
                    f"P{PAIR_NUMBER[pair_id]}: {sign}{target_kw:.1f} kW "
                    f"{direction} accepted directly (attempt {attempt}/2)"
                )
                wait_pair(
                    pair_id,
                    lambda value: target_tracking(value, direction, target_kw),
                    f"{direction} power tracking",
                    POWER_TRACK_TIMEOUT_SECONDS,
                )
                return True
            except GatewayUnavailable:
                raise
            except Exception as error:
                last_error = error
                latest = CLIENT.pair_status(pair_id, include_soc=False)
                if target_tracking(latest, direction, target_kw):
                    return True
                can_retry = attempt == 1 and ready_zero(latest, direction)
                log(
                    f"P{PAIR_NUMBER[pair_id]}: direct set-power attempt {attempt} "
                    f"failed; can_retry={can_retry}; error={error}"
                )
                if can_retry:
                    STOP_REQUESTED.wait(3)
                    continue
                break
        log(
            f"P{PAIR_NUMBER[pair_id]}: staged start failed ({last_error}); "
            "switching to direct automatic-start recovery"
        )

    # Recovery path mirrors the individual command that was field-tested. It is
    # allowed only after the pair is returned to a known stopped baseline.
    current = CLIENT.pair_status(pair_id, include_soc=False)
    if not fully_stopped(current):
        if not safe_stop_pair(pair_id, f"baseline before direct {direction} start"):
            return False
    try:
        HARDWARE_MAY_BE_ACTIVE = True
        return automatic_start_direct(pair_id, direction, target_kw)
    except GatewayUnavailable:
        raise
    except Exception as error:
        log(f"P{PAIR_NUMBER[pair_id]}: direct automatic-start failed: {error}")
        safe_stop_pair(pair_id, f"direct {direction} start failure")
        return False


def violation(item: PairStatus, direction: str, target_kw: float) -> tuple[str | None, bool]:
    if item.soc is None:
        return "SOC unavailable", False
    if direction == "charge" and item.soc >= CHARGE_STOP_SOC:
        return f"SOC {item.soc:.1f}% reached {CHARGE_STOP_SOC:.1f}%", True
    if direction == "discharge" and item.soc <= MIN_DISCHARGE_SOC:
        return f"SOC {item.soc:.1f}% reached {MIN_DISCHARGE_SOC:.1f}%", True
    if item.fault:
        return "PCS/BMS/E-stop fault active", True
    if not bms_connected(item):
        return "BMS contactor/precharge readiness lost", True
    if not direction_allowed(item, direction):
        return f"BMS {direction} current permission lost", True
    if not target_tracking(item, direction, target_kw):
        return "power not tracking target", False
    if item.errors:
        return "cached control status contains read errors", False
    return None, False


def current_rss_mb() -> float:
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return float(line.split()[1]) / 1024.0
    except Exception:
        pass
    return -1.0


def monitor_active_session(
    day: date,
    direction: str,
    times: SessionTimes,
    target_kw: float,
    active: set[str],
    state: dict[str, Any],
) -> None:
    status_errors = {pair_id: 0 for pair_id in PAIR_IDS}
    power_violations = {pair_id: 0 for pair_id in PAIR_IDS}
    gateway_outage_started: float | None = None
    soc_snapshot_errors = 0
    next_memory_log = time.monotonic()

    while datetime.now(IST) < times.stop:
        check_stop()
        update_state(
            state,
            phase=direction,
            day=day,
            direction=direction,
            active=active,
        )

        # Exactly one all-rack SOC request per monitor cycle. A failed refresh is
        # not retried separately by every pair, which prevents an outage from
        # multiplying into a request burst.
        try:
            CLIENT.refresh_soc_snapshot(force=True)
            soc_snapshot_errors = 0
            gateway_outage_started = None
        except GatewayUnavailable as error:
            if gateway_outage_started is None:
                gateway_outage_started = time.monotonic()
                log(f"Gateway outage detected during active {direction}: {error}")
            outage = time.monotonic() - gateway_outage_started
            if outage >= GATEWAY_ACTIVE_OUTAGE_LIMIT_SECONDS:
                if not recover_gateway_and_safe_stop(
                    f"active {direction} API outage", timeout=None
                ):
                    raise RuntimeError(
                        f"{direction} gateway-outage shutdown remains unverified"
                    )
                active.clear()
                raise SessionAborted(f"{direction} safely aborted after gateway outage")
            STOP_REQUESTED.wait(GATEWAY_RETRY_SECONDS)
            continue
        except Exception as error:
            soc_snapshot_errors += 1
            log(
                f"Shared SOC snapshot warning "
                f"{soc_snapshot_errors}/{SOC_ERROR_LIMIT}: {error}"
            )
            if soc_snapshot_errors >= SOC_ERROR_LIMIT:
                if not safe_stop_all_sequential(
                    f"repeated shared SOC snapshot errors during {direction}"
                ):
                    raise RuntimeError(
                        f"{direction} SOC-error shutdown remains unverified"
                    )
                active.clear()
                raise SessionAborted(
                    f"{direction} safely aborted after repeated SOC errors"
                )

        gateway_failed = False
        for pair_id in list(sorted(active)):
            check_stop()
            try:
                item = CLIENT.pair_status(
                    pair_id,
                    include_soc=True,
                    allow_soc_refresh=False,
                )
                print_status(item)
                gateway_outage_started = None
                status_errors[pair_id] = 0
            except GatewayUnavailable as error:
                if gateway_outage_started is None:
                    gateway_outage_started = time.monotonic()
                    log(f"Gateway outage detected during active {direction}: {error}")
                outage = time.monotonic() - gateway_outage_started
                if outage >= GATEWAY_ACTIVE_OUTAGE_LIMIT_SECONDS:
                    if not recover_gateway_and_safe_stop(
                        f"active {direction} API outage", timeout=None
                    ):
                        raise RuntimeError(
                            f"{direction} gateway-outage shutdown remains unverified"
                        )
                    active.clear()
                    raise SessionAborted(
                        f"{direction} safely aborted after gateway outage"
                    )
                gateway_failed = True
                break
            except Exception as error:
                status_errors[pair_id] += 1
                log(
                    f"P{PAIR_NUMBER[pair_id]}: monitor warning "
                    f"{status_errors[pair_id]}/{STATUS_ERROR_LIMIT}: {error}"
                )
                if status_errors[pair_id] >= STATUS_ERROR_LIMIT:
                    if safe_stop_pair(pair_id, "repeated status/SOC errors"):
                        active.discard(pair_id)
                continue

            reason, immediate = violation(item, direction, target_kw)
            if reason is None:
                power_violations[pair_id] = 0
                continue
            if immediate:
                log(f"P{PAIR_NUMBER[pair_id]}: immediate removal: {reason}")
                if safe_stop_pair(pair_id, reason):
                    active.discard(pair_id)
                continue
            power_violations[pair_id] += 1
            log(
                f"P{PAIR_NUMBER[pair_id]}: monitor violation "
                f"{power_violations[pair_id]}/{POWER_VIOLATION_LIMIT}: {reason}"
            )
            if power_violations[pair_id] >= POWER_VIOLATION_LIMIT:
                if safe_stop_pair(pair_id, reason):
                    active.discard(pair_id)

        remaining = (times.stop - datetime.now(IST)).total_seconds()
        if remaining <= 0:
            break
        delay = GATEWAY_RETRY_SECONDS if gateway_failed else MONITOR_CYCLE_SECONDS
        STOP_REQUESTED.wait(min(delay, remaining))
        if time.monotonic() >= next_memory_log:
            gc.collect()
            rss = current_rss_mb()
            log(f"Scheduler memory RSS={rss:.1f} MB; active={sorted(active)}")
            next_memory_log = time.monotonic() + MEMORY_LOG_INTERVAL_SECONDS


def sleep_until(target: datetime) -> None:
    while True:
        check_stop()
        remaining = (target - datetime.now(IST)).total_seconds()
        if remaining <= 0:
            return
        STOP_REQUESTED.wait(min(30, remaining))


def inspect_pairs(include_soc: bool = True) -> dict[str, PairStatus]:
    result: dict[str, PairStatus] = {}
    for index, pair_id in enumerate(PAIR_IDS):
        result[pair_id] = CLIENT.pair_status(
            pair_id, include_soc=include_soc, force_soc=bool(include_soc and index == 0)
        )
        print_status(result[pair_id])
        if index + 1 < len(PAIR_IDS):
            time.sleep(PAIR_COMMAND_SPACING_SECONDS)
    return result


def run_session(day: date, direction: str, state: dict[str, Any]) -> None:
    key = session_key(day, direction)
    if key in set(state.get("completed_sessions") or []):
        return
    times = session_times(day, direction)
    target_kw = CHARGE_KW if direction == "charge" else DISCHARGE_KW
    now = datetime.now(IST)

    if now >= times.stop:
        log(f"Skipping expired session {key}")
        mark_complete(state, day, direction)
        return

    # Restart within an active window: adopt already-active pairs only. Do not
    # start stopped pairs late, because exact preparation was missed.
    if now >= times.start:
        log(f"Scheduler entered during active {direction} window; adopt-only mode")
        snapshots = inspect_pairs(include_soc=True)
        active = {
            pair_id
            for pair_id, item in snapshots.items()
            if target_tracking(item, direction, target_kw)
            and soc_allows(item, direction)
        }
        for pair_id, item in snapshots.items():
            if pair_id not in active and not fully_stopped(item):
                safe_stop_pair(pair_id, "restart reconciliation during active window")
        if active:
            log(f"Adopted active {direction} pairs: {sorted(active)}")
            monitor_active_session(day, direction, times, target_kw, active, state)
        log(f"{direction.capitalize()} stop boundary reached: {times.stop.isoformat()}")
        if not safe_stop_all_sequential(f"scheduled {direction} stop"):
            raise RuntimeError("scheduled safe-stop could not be verified")
        mark_complete(state, day, direction)
        return

    if now < times.prepare:
        update_state(state, phase=f"waiting_{direction}_preparation", day=day, direction=direction)
        log(f"Waiting for {direction} preparation at {times.prepare.isoformat()}")
        sleep_until(times.prepare)

    update_state(state, phase=f"preparing_{direction}", day=day, direction=direction)
    prepared: set[str] = set()
    for pair_id in PAIR_IDS:
        check_stop()
        try:
            if prepare_pair(pair_id, direction):
                prepared.add(pair_id)
        except GatewayUnavailable:
            if not recover_gateway_and_safe_stop(
                f"gateway outage during {direction} preparation", timeout=None
            ):
                raise RuntimeError(
                    f"{direction} preparation outage shutdown remains unverified"
                )
            prepared.clear()
            raise SessionAborted(
                f"{direction} preparation safely aborted after gateway outage"
            )
        update_state(
            state,
            phase=f"preparing_{direction}",
            day=day,
            direction=direction,
            prepared=prepared,
        )
        time.sleep(PAIR_COMMAND_SPACING_SECONDS)

    log(f"Prepared pairs for {direction}: {sorted(prepared)}")
    latest_start = times.stop - timedelta(seconds=MIN_START_REMAINING_SECONDS)
    if datetime.now(IST) >= latest_start:
        log(
            f"Skipping {direction} power start because less than "
            f"{MIN_START_REMAINING_SECONDS}s remains before stop"
        )
        if not safe_stop_all_sequential(f"late {direction} preparation cleanup"):
            raise RuntimeError("late-preparation cleanup could not be verified")
        mark_complete(state, day, direction)
        return

    sleep_until(times.start)
    log(f"{direction.capitalize()} start boundary reached: {times.start.isoformat()}")

    active: set[str] = set()
    prepared_order = sorted(prepared)
    for index, pair_id in enumerate(prepared_order):
        check_stop()
        if datetime.now(IST) >= latest_start:
            remaining_pairs = prepared_order[index:]
            log(
                f"No new {direction} starts: stop guard reached; "
                f"returning prepared pairs to safe baseline: {remaining_pairs}"
            )
            for pending_pair in remaining_pairs:
                if not safe_stop_pair(pending_pair, f"{direction} start-time guard"):
                    raise RuntimeError(
                        f"{pending_pair} start-time-guard safe-stop is unverified"
                    )
                time.sleep(PAIR_COMMAND_SPACING_SECONDS)
            break
        try:
            if start_power_pair(pair_id, direction, target_kw):
                active.add(pair_id)
        except GatewayUnavailable:
            if not recover_gateway_and_safe_stop(
                f"gateway outage during {direction} start", timeout=None
            ):
                raise RuntimeError(
                    f"{direction} start outage shutdown remains unverified"
                )
            active.clear()
            raise SessionAborted(
                f"{direction} start safely aborted after gateway outage"
            )
        update_state(
            state,
            phase=direction,
            day=day,
            direction=direction,
            prepared=prepared,
            active=active,
        )
        time.sleep(PAIR_COMMAND_SPACING_SECONDS)

    log(f"Active {direction} pairs: {sorted(active)}")
    if active:
        monitor_active_session(day, direction, times, target_kw, active, state)
    else:
        log(f"No pair entered {direction}; waiting for scheduled stop boundary")
        sleep_until(times.stop)

    log(f"{direction.capitalize()} stop boundary reached: {times.stop.isoformat()}")
    if not safe_stop_all_sequential(f"scheduled {direction} stop"):
        raise RuntimeError("scheduled safe-stop could not be verified")
    mark_complete(state, day, direction)


def validate_capabilities() -> None:
    cap = CLIENT.capabilities()
    if not cap.get("enabled"):
        raise RuntimeError("backend control sequence is disabled")
    modes = cap.get("modes") or {}
    if not modes.get("safe_stop_monitor_quiesce"):
        raise RuntimeError(
            "backend does not advertise safe-stop monitor quiesce"
        )
    version = str(cap.get("version") or "")
    if not version.startswith("3.0.2"):
        raise RuntimeError(f"backend version {version!r} is not V3.0.2")
    enabled_pairs = {
        str(item.get("pair_id"))
        for item in cap.get("pairs", [])
        if item.get("enabled")
    }
    missing = set(PAIR_IDS) - enabled_pairs
    if missing:
        raise RuntimeError(f"missing enabled pairs: {sorted(missing)}")
    maximum = float((cap.get("safety_limits") or {}).get("max_abs_power_kw") or 0)
    if maximum < max(CHARGE_KW, DISCHARGE_KW):
        raise RuntimeError("backend max power is below requested target")
    if cap.get("confirmation_phrase") != STAGE_CONFIRMATION:
        raise RuntimeError("backend confirmation phrase mismatch")
    log(
        f"Backend validated: controller={cap.get('controller')}, "
        f"version={version}, pairs={sorted(enabled_pairs)}"
    )


def startup_safe_reconcile() -> None:
    """Outside a configured active window, require all pairs to be stopped."""
    now = datetime.now(IST)
    active_window = False
    for day in SCHEDULE_DATES:
        for direction in ("charge", "discharge"):
            times = session_times(day, direction)
            if times.start <= now < times.stop:
                active_window = True
    if active_window:
        return
    snapshots = inspect_pairs(include_soc=False)
    unsafe = [pair_id for pair_id, item in snapshots.items() if not fully_stopped(item)]
    if unsafe:
        log(f"Startup reconciliation found non-stopped pairs outside a window: {unsafe}")
        if not safe_stop_all_sequential("startup reconciliation outside schedule window"):
            raise RuntimeError("startup reconciliation safe-stop failed")
    else:
        log("Startup reconciliation: all four pairs are safely stopped")


def run_scheduler() -> None:
    validate_configuration()
    acquire_lock()
    state = load_state()
    CLIENT.wait_available("scheduler startup", timeout=None)
    validate_capabilities()
    startup_safe_reconcile()
    log(f"Lean sequential scheduler armed; build={SCHEDULER_BUILD}")

    for day in SCHEDULE_DATES:
        for direction in ("charge", "discharge"):
            if STOP_REQUESTED.is_set():
                raise OperatorStop("operator stop requested")
            try:
                run_session(day, direction, state)
            except SessionAborted as error:
                log(str(error))
                mark_complete(state, day, direction)

    update_state(state, phase="completed")
    log("Configured schedule completed; all sessions finished")


def validate_read_only() -> None:
    validate_configuration()
    CLIENT.wait_available("read-only validation", timeout=120)
    validate_capabilities()
    inspect_pairs(include_soc=True)
    log("Read-only validation passed; no control write was sent")


def print_schedule() -> None:
    for day in SCHEDULE_DATES:
        for direction in ("charge", "discharge"):
            times = session_times(day, direction)
            target = CHARGE_KW if direction == "charge" else DISCHARGE_KW
            print(
                f"{day.isoformat()} {direction}: prepare={times.prepare.isoformat()} "
                f"start={times.start.isoformat()} stop={times.stop.isoformat()} "
                f"target={target:.1f} kW/pair"
            )


def self_test() -> None:
    # Pure, offline checks. These do not contact the gateway.
    charge = session_times(date(2026, 8, 4), "charge")
    discharge = session_times(date(2026, 8, 4), "discharge")
    assert charge.prepare.strftime("%H:%M") == "09:20"
    assert charge.start.strftime("%H:%M") == "10:00"
    assert charge.stop.strftime("%H:%M") == "13:30"
    assert discharge.prepare.strftime("%H:%M") == "16:20"
    assert discharge.start.strftime("%H:%M") == "17:00"
    assert discharge.stop.strftime("%H:%M") == "19:00"
    safe = PairStatus(
        "pair_1", 50.0, 0, False, False, 1, 0.0, 0.0, 0.0, 0.0,
        False, False, [], "idle", "stopped", {}
    )
    prepared = PairStatus(
        "pair_1", 50.0, 3, True, True, 16, 0.0, 0.0, 178.0, 178.0,
        False, True, [], "idle", "ready", {}
    )
    active = PairStatus(
        "pair_1", 50.0, 3, True, True, 80, 200.0, 199.0, 178.0, 178.0,
        False, True, [], "success", "complete", {}
    )
    assert fully_stopped(safe)
    assert ready_zero(prepared, "discharge")
    assert target_tracking(active, "discharge", 200.0)
    assert not target_tracking(active, "charge", 125.0)
    print(f"SELF-TEST PASS: {SCHEDULER_BUILD}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--print-schedule", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--safe-stop-now", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.print_schedule:
        validate_configuration()
        print_schedule()
        return 0
    if args.validate_only:
        validate_read_only()
        return 0
    if args.safe_stop_now:
        # Emergency/ExecStopPost protection must not be blocked by schedule,
        # arming, or free-disk validation. It only needs the backend API and
        # control capability checks.
        if not CLIENT.wait_available(
            "manual safe-stop", timeout=SAFE_STOP_NOW_GATEWAY_WAIT_SECONDS
        ):
            log("CRITICAL: manual safe-stop could not reach the gateway")
            return 2
        validate_capabilities()
        return 0 if safe_stop_all_sequential("manual --safe-stop-now") else 2

    exit_code = 0
    try:
        run_scheduler()
    except OperatorStop:
        log("Operator stop received")
    except Exception as error:
        exit_code = 1
        log(f"SUPERVISOR ERROR: {error}")
    finally:
        # Never leave a possibly active pair solely because the Python process is
        # exiting. If the API is down, wait for it and stop as soon as it returns.
        if HARDWARE_MAY_BE_ACTIVE or STOP_REQUESTED.is_set() or exit_code:
            try:
                if not CLIENT.wait_available(
                    "process exit protection", timeout=EXIT_SAFE_STOP_RECOVERY_SECONDS
                ):
                    log("CRITICAL: process exit safe-stop could not reach gateway")
                    return 2
                if not safe_stop_all_sequential("process exit/final protection"):
                    return 2
            except Exception as error:
                log(f"CRITICAL: final protection failed: {error}")
                return 2
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
