#!/usr/bin/env python3
"""Seven-day BESS scheduler for the Kinetics Gateway V3 control API.

This scheduler deliberately does not write Modbus registers directly and does not
call the legacy control_sequence_cli.py helper.  All BMS/PCS writes go through the
field-validated backend control-sequence API contained in the supplied
kinetics_gateway_post_v3 release.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
PAIR_IDS = ("pair_1", "pair_2", "pair_3", "pair_4")
PAIR_NUMBER = {pair_id: index for index, pair_id in enumerate(PAIR_IDS, start=1)}

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
API_USER = os.environ["API_USER"]
API_PASS = os.environ["API_PASS"]

CHARGE_START_TIME = os.environ.get("CHARGE_START_TIME", "11:15")
CHARGE_STOP_TIME = os.environ.get("CHARGE_STOP_TIME", "12:45")
DISCHARGE_START_TIME = os.environ.get("DISCHARGE_START_TIME", "17:00")
DISCHARGE_STOP_TIME = os.environ.get("DISCHARGE_STOP_TIME", "18:45")

CHARGE_KW = float(os.environ.get("CHARGE_KW", "100.0"))
DISCHARGE_KW = float(os.environ.get("DISCHARGE_KW", "200.0"))
CHARGE_STOP_SOC = float(os.environ.get("CHARGE_STOP_SOC", "96.0"))
MIN_DISCHARGE_SOC = float(os.environ.get("MIN_DISCHARGE_SOC", "20.0"))
SITE_MAX_TOTAL_POWER_KW = float(os.environ.get("SITE_MAX_TOTAL_POWER_KW", "1000.0"))

PREPARE_LEAD_MINUTES = int(os.environ.get("PREPARE_LEAD_MINUTES", "20"))
PREPARE_MAX_WORKERS = int(os.environ.get("PREPARE_MAX_WORKERS", "4"))
START_MAX_WORKERS = int(os.environ.get("START_MAX_WORKERS", "4"))
ZERO_MAX_WORKERS = int(os.environ.get("ZERO_MAX_WORKERS", "4"))

PREPARE_POLL_SECONDS = float(os.environ.get("PREPARE_POLL_SECONDS", "1"))
MONITOR_POLL_SECONDS = float(os.environ.get("MONITOR_POLL_SECONDS", "5"))
START_GUARD_SECONDS = int(os.environ.get("START_GUARD_SECONDS", "5"))
STOP_GUARD_SECONDS = int(os.environ.get("STOP_GUARD_SECONDS", "5"))
POWER_TRACK_TIMEOUT_SECONDS = int(os.environ.get("POWER_TRACK_TIMEOUT_SECONDS", "120"))
POWER_TRACK_MIN_FRACTION = float(os.environ.get("POWER_TRACK_MIN_FRACTION", "0.75"))
NORMAL_CATCHUP_MINUTES = int(os.environ.get("NORMAL_CATCHUP_MINUTES", "10"))
MIN_REMAINING_SESSION_MINUTES = int(os.environ.get("MIN_REMAINING_SESSION_MINUTES", "15"))
STATUS_ERROR_LIMIT = int(os.environ.get("STATUS_ERROR_LIMIT", "3"))
POWER_VIOLATION_LIMIT = int(os.environ.get("POWER_VIOLATION_LIMIT", "3"))

ROOT_MIN_FREE_MB = int(os.environ.get("ROOT_MIN_FREE_MB", "512"))
REQUIRE_NTP_SYNC = os.environ.get("REQUIRE_NTP_SYNC", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

STAGE_CONFIRMATION = os.environ.get("STAGE_CONFIRMATION", "EXECUTE_STAGE_WRITE")
ARM_PHRASE = os.environ.get("ARM_PHRASE", "")
REQUIRED_ARM_PHRASE = "EXECUTE_7_DAY_BACKEND_V3_SCHEDULE"

STATE_DIR = Path(
    os.environ.get(
        "STATE_DIR",
        "/mnt/ems-logs/scheduler/bess-seven-day-backend-v3",
    )
)
STATE_FILE = STATE_DIR / "state.json"
LOCK_FILE = Path(os.environ.get("LOCK_FILE", "/run/bess-seven-day-backend-v3.lock"))

TOKEN: str | None = None
TOKEN_LOCK = threading.Lock()
LOG_LOCK = threading.Lock()
STATE_LOCK = threading.Lock()
STOP_REQUESTED = threading.Event()
SESSION_STOPPING = threading.Event()
SAFE_STOP_LOCK = threading.Lock()
HARDWARE_TOUCHED = False
LOCK_HANDLE: Any = None


class OperatorStop(Exception):
    """Raised when systemd/operator requests a graceful stop."""


@dataclass(frozen=True)
class SessionTimes:
    prepare: datetime
    start: datetime
    stop: datetime


@dataclass
class PairSnapshot:
    pair_id: str
    summary: dict[str, Any]
    status: dict[str, Any]
    soc: float


def log(message: str) -> None:
    stamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S %Z")
    with LOG_LOCK:
        print(f"[{stamp}] {message}", flush=True)


def signal_handler(signum: int, _frame: Any) -> None:
    STOP_REQUESTED.set()
    SESSION_STOPPING.set()
    log(f"Signal {signum} received; graceful backend safe-stop requested")


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def check_operator_stop() -> None:
    if STOP_REQUESTED.is_set():
        raise OperatorStop("Operator safe-stop requested")


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
        raise ValueError(f"Unsupported direction: {direction}")
    return SessionTimes(
        prepare=start - timedelta(minutes=PREPARE_LEAD_MINUTES),
        start=start,
        stop=stop,
    )


def schedule_dates() -> list[date]:
    explicit = os.environ.get("SCHEDULE_DATES", "").strip()
    if explicit:
        days = sorted(
            {
                date.fromisoformat(item.strip())
                for item in explicit.split(",")
                if item.strip()
            }
        )
    else:
        start_text = os.environ.get("SCHEDULE_START_DATE", "").strip()
        start_day = (
            date.fromisoformat(start_text)
            if start_text
            else datetime.now(IST).date() + timedelta(days=1)
        )
        count = int(os.environ.get("SCHEDULE_DAYS", "7"))
        days = [start_day + timedelta(days=index) for index in range(count)]
    return days


SCHEDULE_DATES = schedule_dates()


def session_key(day: date, direction: str) -> str:
    return f"{day.isoformat()}:{direction}"


def acquire_process_lock() -> None:
    global LOCK_HANDLE
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_HANDLE = LOCK_FILE.open("w", encoding="utf-8")
    try:
        fcntl.flock(LOCK_HANDLE.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        raise RuntimeError("Another seven-day scheduler instance is already running") from error
    LOCK_HANDLE.write(str(os.getpid()))
    LOCK_HANDLE.flush()


def root_free_mb() -> float:
    usage = shutil.disk_usage("/")
    return usage.free / (1024 * 1024)


def require_storage_ready() -> None:
    if not os.path.ismount("/mnt/ems-logs"):
        raise RuntimeError("/mnt/ems-logs is not mounted; refusing scheduled control")
    free_mb = root_free_mb()
    if free_mb < ROOT_MIN_FREE_MB:
        raise RuntimeError(
            f"Root filesystem has only {free_mb:.0f} MB free; "
            f"minimum is {ROOT_MIN_FREE_MB} MB"
        )
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(STATE_DIR, 0o700)


def ntp_is_synchronized() -> bool:
    if not REQUIRE_NTP_SYNC:
        return True
    try:
        result = subprocess.run(
            ["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip().lower() == "yes"


def validate_configuration() -> None:
    if ARM_PHRASE != REQUIRED_ARM_PHRASE:
        raise RuntimeError("ARM_PHRASE is incorrect; no hardware command will be sent")
    if len(SCHEDULE_DATES) != 7:
        raise RuntimeError("Exactly seven unique schedule dates are required")
    for previous, current in zip(SCHEDULE_DATES, SCHEDULE_DATES[1:]):
        if current != previous + timedelta(days=1):
            raise RuntimeError("Schedule dates must be seven consecutive calendar days")
    if not 0 < MIN_DISCHARGE_SOC < CHARGE_STOP_SOC <= 100:
        raise RuntimeError("Require 0 < MIN_DISCHARGE_SOC < CHARGE_STOP_SOC <= 100")
    for name, power in (("CHARGE_KW", CHARGE_KW), ("DISCHARGE_KW", DISCHARGE_KW)):
        if not 0 < power <= 240:
            raise RuntimeError(f"{name} must be greater than 0 and at most 240 kW")
        if power * len(PAIR_IDS) > SITE_MAX_TOTAL_POWER_KW:
            raise RuntimeError(
                f"{name} total {power * len(PAIR_IDS):.1f} kW exceeds "
                f"site limit {SITE_MAX_TOTAL_POWER_KW:.1f} kW"
            )
    if not 1 <= PREPARE_MAX_WORKERS <= 4:
        raise RuntimeError("PREPARE_MAX_WORKERS must be between 1 and 4")
    if not 1 <= START_MAX_WORKERS <= 4:
        raise RuntimeError("START_MAX_WORKERS must be between 1 and 4")
    if not 1 <= ZERO_MAX_WORKERS <= 4:
        raise RuntimeError("ZERO_MAX_WORKERS must be between 1 and 4")
    if PREPARE_LEAD_MINUTES < 5:
        raise RuntimeError("PREPARE_LEAD_MINUTES must be at least 5")
    if not 0.1 <= POWER_TRACK_MIN_FRACTION <= 1.0:
        raise RuntimeError("POWER_TRACK_MIN_FRACTION must be between 0.1 and 1.0")
    if STATUS_ERROR_LIMIT < 1 or POWER_VIOLATION_LIMIT < 1:
        raise RuntimeError("Violation limits must be at least 1")

    for day in SCHEDULE_DATES:
        charge = session_times(day, "charge")
        discharge = session_times(day, "discharge")
        if not charge.prepare < charge.start < charge.stop:
            raise RuntimeError(f"Invalid charging times for {day}")
        if not discharge.prepare < discharge.start < discharge.stop:
            raise RuntimeError(f"Invalid discharging times for {day}")
        if charge.stop > discharge.prepare:
            raise RuntimeError(f"Charging overlaps discharge preparation on {day}")

    require_storage_ready()
    if not ntp_is_synchronized():
        raise RuntimeError("System clock is not NTP synchronized; refusing timed operation")

    log(
        "Configuration valid: "
        f"dates={[str(item) for item in SCHEDULE_DATES]}, "
        f"charge={CHARGE_START_TIME}-{CHARGE_STOP_TIME} at {CHARGE_KW:.1f} kW/pair, "
        f"discharge={DISCHARGE_START_TIME}-{DISCHARGE_STOP_TIME} "
        f"at {DISCHARGE_KW:.1f} kW/pair, prepare_workers={PREPARE_MAX_WORKERS}"
    )


def default_state() -> dict[str, Any]:
    return {
        "version": 4,
        "backend_profile": "kinetics_gateway_post_v3",
        "schedule_dates": [item.isoformat() for item in SCHEDULE_DATES],
        "phase": "waiting",
        "current_date": None,
        "current_session": None,
        "prepared_pairs": [],
        "active_pairs": [],
        "window_start": None,
        "window_stop": None,
        "completed_sessions": [],
        "completed": False,
        "last_update": datetime.now(IST).isoformat(),
    }


def save_state(state: dict[str, Any]) -> None:
    with STATE_LOCK:
        require_storage_ready()
        state["last_update"] = datetime.now(IST).isoformat()
        temporary = STATE_FILE.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, STATE_FILE)


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        state = default_state()
        save_state(state)
        return state
    try:
        with STATE_FILE.open(encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        corrupt = STATE_FILE.with_name(f"state.corrupt.{int(time.time())}.json")
        os.replace(STATE_FILE, corrupt)
        log(f"Archived unreadable state as {corrupt}: {error}")
        state = default_state()
        save_state(state)
        return state
    if state.get("version") != 4 or state.get("schedule_dates") != [
        item.isoformat() for item in SCHEDULE_DATES
    ]:
        legacy = STATE_FILE.with_name(f"state.legacy.{int(time.time())}.json")
        os.replace(STATE_FILE, legacy)
        log(f"Archived incompatible state as {legacy}")
        state = default_state()
        save_state(state)
    return state


def update_session_state(
    state: dict[str, Any],
    day: date,
    direction: str,
    phase: str,
    prepared: Iterable[str] = (),
    active: Iterable[str] = (),
) -> None:
    times = session_times(day, direction)
    state.update(
        {
            "phase": phase,
            "current_date": day.isoformat(),
            "current_session": direction,
            "prepared_pairs": sorted(set(prepared)),
            "active_pairs": sorted(set(active)),
            "window_start": times.start.isoformat(),
            "window_stop": times.stop.isoformat(),
        }
    )
    save_state(state)


def mark_session_complete(state: dict[str, Any], day: date, direction: str) -> None:
    completed = set(state.get("completed_sessions") or [])
    completed.add(session_key(day, direction))
    state.update(
        {
            "phase": "waiting",
            "current_date": day.isoformat(),
            "current_session": None,
            "prepared_pairs": [],
            "active_pairs": [],
            "window_start": None,
            "window_stop": None,
            "completed_sessions": sorted(completed),
        }
    )
    save_state(state)


def login() -> None:
    global TOKEN
    payload = json.dumps({"username": API_USER, "password": API_PASS}).encode()
    request = urllib.request.Request(
        f"{BASE_URL}/api/auth/login",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    token = result.get("access_token")
    if not token:
        raise RuntimeError("Backend login response did not contain access_token")
    with TOKEN_LOCK:
        TOKEN = str(token)
    log(f"Gateway authentication successful as {result.get('username', API_USER)}")


def current_token() -> str | None:
    with TOKEN_LOCK:
        return TOKEN


def api_json(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: float = 180,
    attempts: int = 3,
) -> dict[str, Any]:
    if current_token() is None:
        login()
    data = None if payload is None else json.dumps(payload).encode()
    last_error: Exception | None = None
    for attempt in range(attempts):
        request = urllib.request.Request(
            f"{BASE_URL}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {current_token()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
                return json.loads(body.decode()) if body else {}
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")
            if error.code == 401 and attempt == 0:
                login()
                continue
            last_error = RuntimeError(f"HTTP {error.code} {path}: {detail}")
            if error.code in {400, 403, 404, 409, 422}:
                raise last_error from error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = RuntimeError(f"API request failed {method} {path}: {error}")
        if attempt + 1 < attempts:
            time.sleep(1.5 * (attempt + 1))
    raise last_error or RuntimeError(f"API request failed {method} {path}")


def validate_backend_capabilities() -> dict[str, Any]:
    capabilities = api_json("GET", "/api/control-sequence/capabilities", timeout=60)
    if not capabilities.get("enabled"):
        raise RuntimeError("Backend control sequence is disabled")
    modes = capabilities.get("modes") or {}
    if not modes.get("parallel_pair_operation"):
        raise RuntimeError("Backend does not advertise parallel pair operation")
    if not modes.get("safe_stop_monitor_quiesce"):
        raise RuntimeError("Backend does not advertise safe-stop monitor quiesce")
    enabled_pairs = {
        str(item.get("pair_id"))
        for item in capabilities.get("pairs", [])
        if item.get("enabled")
    }
    missing = set(PAIR_IDS) - enabled_pairs
    if missing:
        raise RuntimeError(f"Backend is missing enabled pairs: {sorted(missing)}")
    backend_confirmation = capabilities.get("confirmation_phrase")
    if backend_confirmation != STAGE_CONFIRMATION:
        raise RuntimeError(
            f"Backend confirmation phrase is {backend_confirmation!r}, "
            f"scheduler expects {STAGE_CONFIRMATION!r}"
        )
    maximum = float((capabilities.get("safety_limits") or {}).get("max_abs_power_kw") or 0)
    if maximum < max(CHARGE_KW, DISCHARGE_KW):
        raise RuntimeError(
            f"Backend power cap {maximum:.1f} kW is below requested "
            f"{max(CHARGE_KW, DISCHARGE_KW):.1f} kW"
        )
    log(
        f"Backend capabilities validated: controller={capabilities.get('controller')}, "
        f"version={capabilities.get('version')}, enabled_pairs={sorted(enabled_pairs)}"
    )
    return capabilities


def point_value(point: Any) -> Any:
    if isinstance(point, dict):
        if "value" in point:
            return point.get("value")
        if "v" in point:
            return point.get("v")
    return point


def extract_soc(rack: dict[str, Any]) -> float:
    if not rack.get("online", False):
        raise RuntimeError(f"BMS rack {rack.get('rack_id')} is offline")
    telemetry = rack.get("telemetry") or {}
    point = telemetry.get("soc")
    if not isinstance(point, dict):
        raise RuntimeError(f"BMS rack {rack.get('rack_id')} SOC is unavailable")
    quality = str(point.get("quality", point.get("q", "unknown"))).lower()
    if quality not in {"good", "ok"}:
        raise RuntimeError(
            f"BMS rack {rack.get('rack_id')} SOC quality is {quality}"
        )
    raw_value = point_value(point)
    if raw_value is None:
        raise RuntimeError(f"BMS rack {rack.get('rack_id')} SOC value is missing")
    soc = float(raw_value)
    unit = str(point.get("unit") or "")
    # The supplied V3 catalog exposes rack SOC as 0..1000 per-mille with no
    # numeric scale, so cached API values are divided by 10 when needed.
    if "‰" in unit or soc > 100.0:
        soc /= 10.0
    if not 0.0 <= soc <= 100.0:
        raise RuntimeError(f"BMS rack {rack.get('rack_id')} SOC {soc} is invalid")
    return soc


def number(summary: dict[str, Any], key: str) -> float:
    try:
        value = summary.get(key)
        return 0.0 if value is None else float(value)
    except (TypeError, ValueError):
        return 0.0


def integer(summary: dict[str, Any], key: str) -> int:
    return int(number(summary, key))


def blockers(summary: dict[str, Any]) -> dict[str, Any]:
    return summary.get("blockers") or {}


def has_fault(summary: dict[str, Any]) -> bool:
    block = blockers(summary)
    return any(
        (
            bool(summary.get("pcs_fault_shutdown")),
            bool(block.get("system_fault")),
            bool(block.get("documented_critical_fault")),
            bool(block.get("emergency_stop_fault")),
        )
    )


def power_is_zero(summary: dict[str, Any]) -> bool:
    return (
        abs(number(summary, "pcs_power_setpoint_kw")) <= 0.5
        and abs(number(summary, "pcs_actual_power_kw")) <= 1.0
    )


def pcs_is_stopped(summary: dict[str, Any]) -> bool:
    return integer(summary, "pcs_operating_state") == 1 and power_is_zero(summary)


def bms_is_open(summary: dict[str, Any]) -> bool:
    return (
        integer(summary, "precharge_state") == 0
        and not bool(summary.get("positive_contactor_closed"))
        and not bool(summary.get("negative_contactor_closed"))
    )


def fully_stopped(summary: dict[str, Any]) -> bool:
    return pcs_is_stopped(summary) and bms_is_open(summary)


def bms_connected(summary: dict[str, Any]) -> bool:
    return (
        bool(summary.get("precharge_success"))
        and bool(summary.get("contactors_ready"))
        and bool(summary.get("rack_voltage_valid"))
        and not has_fault(summary)
    )


def direction_limit_available(summary: dict[str, Any], direction: str) -> bool:
    if direction == "charge":
        return number(summary, "rack_charge_current_limit_a") > 0.0 and not bool(
            blockers(summary).get("system_charge_prohibited")
        )
    return number(summary, "rack_discharge_current_limit_a") > 0.0 and not bool(
        blockers(summary).get("system_discharge_prohibited")
    )


def ready_zero(summary: dict[str, Any], direction: str) -> bool:
    workflow = summary.get("_workflow") or {}
    return (
        integer(summary, "pcs_operating_state") in {16, 32, 80}
        and bms_connected(summary)
        and direction_limit_available(summary, direction)
        and power_is_zero(summary)
        and not has_fault(summary)
        and (not workflow or bool(workflow.get("ready_for_power")))
    )


def target_tracking(summary: dict[str, Any], direction: str, target_kw: float) -> bool:
    minimum = target_kw * POWER_TRACK_MIN_FRACTION
    setpoint = number(summary, "pcs_power_setpoint_kw")
    actual = number(summary, "pcs_actual_power_kw")
    if direction == "charge":
        return setpoint <= -minimum and actual <= -minimum
    return setpoint >= minimum and actual >= minimum


def print_pair_snapshot(snapshot: PairSnapshot) -> None:
    summary = snapshot.summary
    log(
        f"P{PAIR_NUMBER[snapshot.pair_id]}: SOC={snapshot.soc:.1f}% "
        f"PRE={integer(summary, 'precharge_state')} "
        f"CONTACTORS={bool(summary.get('positive_contactor_closed'))}/"
        f"{bool(summary.get('negative_contactor_closed'))} "
        f"PCS={integer(summary, 'pcs_operating_state')} "
        f"SET={number(summary, 'pcs_power_setpoint_kw'):.1f} kW "
        f"ACT={number(summary, 'pcs_actual_power_kw'):.1f} kW "
        f"CHG_LIMIT={number(summary, 'rack_charge_current_limit_a'):.1f} A "
        f"DSG_LIMIT={number(summary, 'rack_discharge_current_limit_a'):.1f} A "
        f"FAULT={has_fault(summary)}"
    )


def _get_all_pair_snapshots_once() -> dict[str, PairSnapshot]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        status_future = executor.submit(
            api_json,
            "GET",
            "/api/control-sequence/status/all",
            None,
            timeout=60,
        )
        racks_future = executor.submit(
            api_json,
            "GET",
            "/api/bms/racks",
            None,
            timeout=60,
        )
        all_status = status_future.result()
        all_racks = racks_future.result()

    status_map = all_status.get("by_pair_id") or {}
    racks = {
        int(item.get("rack_id")): item
        for item in all_racks.get("racks", [])
        if item.get("rack_id") is not None
    }
    snapshots: dict[str, PairSnapshot] = {}
    for pair_id in PAIR_IDS:
        pair_status = status_map.get(pair_id)
        if not isinstance(pair_status, dict):
            raise RuntimeError(f"Cached control status missing for {pair_id}")
        summary = dict(pair_status.get("summary") or {})
        summary["_workflow"] = pair_status.get("workflow") or {}
        rack_id = int((pair_status.get("pair") or {}).get("rack_id") or PAIR_NUMBER[pair_id])
        rack = racks.get(rack_id)
        if rack is None:
            raise RuntimeError(f"Cached BMS rack {rack_id} missing for {pair_id}")
        snapshots[pair_id] = PairSnapshot(
            pair_id=pair_id,
            summary=summary,
            status=pair_status,
            soc=extract_soc(rack),
        )
    return snapshots


def get_all_pair_snapshots(attempts: int = 3) -> dict[str, PairSnapshot]:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return _get_all_pair_snapshots_once()
        except Exception as error:
            last_error = error
            if attempt < attempts:
                time.sleep(float(attempt))
    raise RuntimeError(f"Unable to obtain complete cached four-pair snapshot: {last_error}")


def get_pair_snapshot(pair_id: str) -> PairSnapshot:
    return get_all_pair_snapshots()[pair_id]


def soc_allows(snapshot: PairSnapshot, direction: str) -> bool:
    if direction == "charge":
        return snapshot.soc < CHARGE_STOP_SOC
    return snapshot.soc > MIN_DISCHARGE_SOC


def require_soc_allows(snapshot: PairSnapshot, direction: str) -> None:
    if not soc_allows(snapshot, direction):
        if direction == "charge":
            raise RuntimeError(
                f"SOC {snapshot.soc:.1f}% is at/above charge cutoff "
                f"{CHARGE_STOP_SOC:.1f}%"
            )
        raise RuntimeError(
            f"SOC {snapshot.soc:.1f}% is at/below discharge cutoff "
            f"{MIN_DISCHARGE_SOC:.1f}%"
        )


def post_stage(pair_id: str, endpoint: str, payload: dict[str, Any] | None = None, *, timeout: float = 300) -> dict[str, Any]:
    body = {"confirmation": STAGE_CONFIRMATION}
    if payload:
        body.update(payload)
    return api_json(
        "POST",
        f"/api/control-sequence/{pair_id}/{endpoint}",
        body,
        timeout=timeout,
    )


def wait_cached(
    pair_id: str,
    predicate: Callable[[PairSnapshot], bool],
    description: str,
    timeout_seconds: float,
    *,
    honor_operator_stop: bool = True,
) -> PairSnapshot:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if honor_operator_stop:
            check_operator_stop()
        try:
            snapshot = get_pair_snapshot(pair_id)
            print_pair_snapshot(snapshot)
            if predicate(snapshot):
                log(f"P{PAIR_NUMBER[pair_id]}: verified {description}")
                return snapshot
            last_error = None
        except Exception as error:
            last_error = error
            log(
                f"P{PAIR_NUMBER[pair_id]}: waiting for {description}; "
                f"cache warning: {error}"
            )
        if honor_operator_stop:
            STOP_REQUESTED.wait(2.0)
        else:
            time.sleep(2.0)
    suffix = f"; last error: {last_error}" if last_error else ""
    raise TimeoutError(
        f"P{PAIR_NUMBER[pair_id]}: timed out waiting for {description}{suffix}"
    )


def safe_stop_pair(pair_id: str, reason: str) -> bool:
    global HARDWARE_TOUCHED
    HARDWARE_TOUCHED = True
    log(f"P{PAIR_NUMBER[pair_id]}: backend safe-stop starting ({reason})")
    try:
        response = post_stage(
            pair_id,
            "safe-stop",
            {"open_bms": True},
            timeout=360,
        )
        if not response.get("ok"):
            raise RuntimeError(json.dumps(response.get("errors") or response, sort_keys=True))
        wait_cached(
            pair_id,
            lambda item: fully_stopped(item.summary),
            "zero power, PCS stopped and BMS contactors open",
            120,
            honor_operator_stop=False,
        )
        log(f"P{PAIR_NUMBER[pair_id]}: backend safe-stop verified")
        return True
    except Exception as error:
        log(f"P{PAIR_NUMBER[pair_id]}: backend safe-stop failed: {error}")
        return False


def zero_power_pair(pair_id: str) -> bool:
    global HARDWARE_TOUCHED
    HARDWARE_TOUCHED = True
    log(f"P{PAIR_NUMBER[pair_id]}: zero-power request")
    try:
        response = post_stage(pair_id, "zero-power", timeout=180)
        if not response.get("ok"):
            raise RuntimeError(json.dumps(response, sort_keys=True))
        log(f"P{PAIR_NUMBER[pair_id]}: zero power verified by backend")
        return True
    except Exception as error:
        log(f"P{PAIR_NUMBER[pair_id]}: zero-power request failed: {error}")
        return False


def run_parallel(
    label: str,
    pairs: Iterable[str],
    worker: Callable[[str], Any],
    max_workers: int,
) -> dict[str, tuple[bool, Any]]:
    selected = list(dict.fromkeys(pairs))
    if not selected:
        return {}
    log(f"{label}: parallel request for {selected}")
    results: dict[str, tuple[bool, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(worker, pair_id): pair_id for pair_id in selected}
        for future in concurrent.futures.as_completed(future_map):
            pair_id = future_map[future]
            try:
                results[pair_id] = (True, future.result())
            except Exception as error:
                results[pair_id] = (False, error)
                log(f"P{PAIR_NUMBER[pair_id]}: {label} failed: {error}")
    return results


def backend_safe_stop_all(reason: str) -> bool:
    global HARDWARE_TOUCHED
    HARDWARE_TOUCHED = True
    with SAFE_STOP_LOCK:
        SESSION_STOPPING.set()
        log(f"All-pair shutdown starting: {reason}")

        zero_results = run_parallel(
            "immediate zero-power",
            PAIR_IDS,
            zero_power_pair,
            ZERO_MAX_WORKERS,
        )
        zero_failures = [pair_id for pair_id, (ok, value) in zero_results.items() if not ok or not value]
        if zero_failures:
            log(f"WARNING: zero-power endpoint failed for {zero_failures}; continuing safe-stop-all")

        try:
            response = api_json(
                "POST",
                "/api/control-sequence/safe-stop-all",
                {"confirmation": STAGE_CONFIRMATION, "open_bms": True},
                timeout=600,
                attempts=2,
            )
            if not response.get("ok"):
                log(
                    "WARNING: backend safe-stop-all incomplete: "
                    + json.dumps(response.get("failures") or response, sort_keys=True)
                )
        except Exception as error:
            response = {"ok": False, "error": str(error)}
            log(f"WARNING: backend safe-stop-all request failed: {error}")

        deadline = time.monotonic() + 180
        remaining = set(PAIR_IDS)
        while time.monotonic() < deadline and remaining:
            try:
                snapshots = get_all_pair_snapshots()
                remaining = {
                    pair_id
                    for pair_id, snapshot in snapshots.items()
                    if not fully_stopped(snapshot.summary)
                }
                for snapshot in snapshots.values():
                    print_pair_snapshot(snapshot)
                if not remaining:
                    log("All four pairs verified at zero power, PCS stopped and contactors open")
                    return True
            except Exception as error:
                log(f"Final all-pair verification warning: {error}")
            time.sleep(3)

        if remaining:
            log(f"Retrying individual backend safe-stop for {sorted(remaining)}")
            retry_results = run_parallel(
                "individual safe-stop recovery",
                sorted(remaining),
                lambda pair_id: safe_stop_pair(pair_id, "safe-stop-all recovery"),
                2,
            )
            failed = [
                pair_id
                for pair_id, (ok, value) in retry_results.items()
                if not ok or not value
            ]
            if failed:
                log(f"CRITICAL: safe shutdown remains unverified for {failed}")
                return False

        try:
            snapshots = get_all_pair_snapshots()
            all_stopped = all(fully_stopped(item.summary) for item in snapshots.values())
        except Exception as error:
            log(f"CRITICAL: final status read failed after shutdown: {error}")
            return False
        if all_stopped:
            log("All-pair backend safe-stop verified")
        return all_stopped


def prepare_pair(pair_id: str, direction: str) -> bool:
    global HARDWARE_TOUCHED
    check_operator_stop()
    if SESSION_STOPPING.is_set():
        raise OperatorStop("Session stop is already in progress")

    snapshot = get_pair_snapshot(pair_id)
    require_soc_allows(snapshot, direction)
    print_pair_snapshot(snapshot)

    if ready_zero(snapshot.summary, direction):
        log(f"P{PAIR_NUMBER[pair_id]}: already ready at zero power for {direction}")
        return True

    HARDWARE_TOUCHED = True
    if not fully_stopped(snapshot.summary):
        if not safe_stop_pair(pair_id, f"baseline before {direction} preparation"):
            raise RuntimeError("baseline safe-stop could not be verified")

    check_operator_stop()
    if SESSION_STOPPING.is_set():
        raise OperatorStop("Session stop began during preparation")
    snapshot = get_pair_snapshot(pair_id)
    require_soc_allows(snapshot, direction)

    log(f"P{PAIR_NUMBER[pair_id]}: configuring PCS at zero power")
    response = post_stage(pair_id, "configure-pcs", timeout=240)
    if not response.get("ok"):
        raise RuntimeError("configure-pcs was not successful")

    check_operator_stop()
    if SESSION_STOPPING.is_set():
        raise OperatorStop("Session stop began during preparation")
    log(f"P{PAIR_NUMBER[pair_id]}: requesting pair-specific BAU precharge")
    response = post_stage(pair_id, "start-precharge", timeout=180)
    if not response.get("ok"):
        raise RuntimeError("start-precharge was not successful")

    wait_cached(
        pair_id,
        lambda item: bms_connected(item.summary),
        "BMS precharge state 3 and both contactors closed",
        120,
    )

    check_operator_stop()
    if SESSION_STOPPING.is_set():
        raise OperatorStop("Session stop began during preparation")
    log(f"P{PAIR_NUMBER[pair_id]}: starting PCS at zero power")
    response = post_stage(pair_id, "start-pcs", timeout=300)
    if not response.get("ok"):
        raise RuntimeError("start-pcs was not successful")

    wait_cached(
        pair_id,
        lambda item: ready_zero(item.summary, direction),
        f"PCS/BMS ready at zero power for {direction}",
        120,
    )
    log(f"P{PAIR_NUMBER[pair_id]}: {direction} preparation complete")
    return True


def start_power_pair(pair_id: str, direction: str, target_kw: float) -> bool:
    global HARDWARE_TOUCHED
    check_operator_stop()
    if SESSION_STOPPING.is_set():
        raise OperatorStop("Session stop is already in progress")
    snapshot = get_pair_snapshot(pair_id)
    require_soc_allows(snapshot, direction)
    if not ready_zero(snapshot.summary, direction):
        raise RuntimeError("pair is not ready at zero power")

    HARDWARE_TOUCHED = True
    response = post_stage(
        pair_id,
        "set-power",
        {"direction": direction, "power_kw": target_kw},
        timeout=240,
    )
    if not response.get("ok"):
        raise RuntimeError("set-power was not successful")
    sign = "-" if direction == "charge" else "+"
    log(f"P{PAIR_NUMBER[pair_id]}: {sign}{target_kw:.1f} kW {direction} accepted")

    wait_cached(
        pair_id,
        lambda item: target_tracking(item.summary, direction, target_kw),
        f"{direction} power tracking at >= {POWER_TRACK_MIN_FRACTION:.0%} target",
        POWER_TRACK_TIMEOUT_SECONDS,
    )
    return True


def early_stop_pair(pair_id: str, reason: str) -> bool:
    log(f"P{PAIR_NUMBER[pair_id]}: early removal from session: {reason}")
    zero_power_pair(pair_id)
    return safe_stop_pair(pair_id, reason)


def pair_violation(snapshot: PairSnapshot, direction: str, target_kw: float) -> str | None:
    summary = snapshot.summary
    if snapshot.status.get("errors"):
        return "cached control status contains read errors"
    if direction == "charge" and snapshot.soc >= CHARGE_STOP_SOC:
        return f"SOC {snapshot.soc:.1f}% reached charge cutoff {CHARGE_STOP_SOC:.1f}%"
    if direction == "discharge" and snapshot.soc <= MIN_DISCHARGE_SOC:
        return (
            f"SOC {snapshot.soc:.1f}% reached discharge cutoff "
            f"{MIN_DISCHARGE_SOC:.1f}%"
        )
    if has_fault(summary):
        return "PCS/BMS/E-stop fault is active"
    if not bms_connected(summary):
        return "BMS precharge/contactors readiness was lost"
    if not direction_limit_available(summary, direction):
        return f"BMS {direction} current/power permission was lost"
    if not target_tracking(summary, direction, target_kw):
        return f"{direction} power is not tracking the requested target"
    return None


def detect_existing_session_state(direction: str, target_kw: float) -> tuple[set[str], set[str]]:
    active: set[str] = set()
    prepared: set[str] = set()
    snapshots = get_all_pair_snapshots()
    for pair_id, snapshot in snapshots.items():
        print_pair_snapshot(snapshot)
        if not soc_allows(snapshot, direction):
            continue
        if target_tracking(snapshot.summary, direction, target_kw):
            active.add(pair_id)
        elif ready_zero(snapshot.summary, direction):
            prepared.add(pair_id)
    return active, prepared


def sleep_until(target: datetime) -> None:
    while True:
        check_operator_stop()
        remaining = (target - datetime.now(IST)).total_seconds()
        if remaining <= 0:
            return
        STOP_REQUESTED.wait(min(remaining, 1.0))


def harvest_futures(
    futures: dict[str, concurrent.futures.Future[Any]],
    completed: set[str],
    failed: set[str],
    label: str,
) -> None:
    for pair_id, future in list(futures.items()):
        if pair_id in completed or pair_id in failed or not future.done():
            continue
        try:
            result = future.result()
            if result:
                completed.add(pair_id)
                log(f"P{PAIR_NUMBER[pair_id]}: {label} completed")
            else:
                failed.add(pair_id)
                log(f"P{PAIR_NUMBER[pair_id]}: {label} returned unsuccessful")
        except Exception as error:
            failed.add(pair_id)
            log(f"P{PAIR_NUMBER[pair_id]}: {label} failed: {error}")


def run_session(day: date, direction: str, state: dict[str, Any]) -> None:
    key = session_key(day, direction)
    if key in set(state.get("completed_sessions") or []):
        return

    times = session_times(day, direction)
    target_kw = CHARGE_KW if direction == "charge" else DISCHARGE_KW
    now = datetime.now(IST)
    if now >= times.stop:
        log(f"Skipping expired session {key}; ensuring all pairs are safely stopped")
        if not backend_safe_stop_all(f"expired session recovery {key}"):
            raise RuntimeError(f"Could not verify safe-stop after expired session {key}")
        mark_session_complete(state, day, direction)
        SESSION_STOPPING.clear()
        return

    if now < times.prepare:
        update_session_state(state, day, direction, f"waiting_{direction}_preparation")
        log(f"Waiting for {direction} preparation at {times.prepare.isoformat()}")
        sleep_until(times.prepare)

    check_operator_stop()
    require_storage_ready()
    if not ntp_is_synchronized():
        raise RuntimeError("System clock lost NTP synchronization before session")
    SESSION_STOPPING.clear()
    update_session_state(state, day, direction, f"preparing_{direction}")

    active, prepared = detect_existing_session_state(direction, target_kw)
    if active:
        log(f"Recovered already active {direction} pairs: {sorted(active)}")
    if prepared:
        log(f"Recovered already prepared {direction} pairs: {sorted(prepared)}")

    candidates: list[str] = []
    snapshots = get_all_pair_snapshots()
    for pair_id, snapshot in snapshots.items():
        if pair_id in active or pair_id in prepared:
            continue
        if soc_allows(snapshot, direction):
            candidates.append(pair_id)
        else:
            log(
                f"P{PAIR_NUMBER[pair_id]}: excluded from {direction}; "
                f"SOC={snapshot.soc:.1f}%"
            )

    prep_executor = concurrent.futures.ThreadPoolExecutor(max_workers=PREPARE_MAX_WORKERS)
    prep_futures = {
        pair_id: prep_executor.submit(prepare_pair, pair_id, direction)
        for pair_id in candidates
    }
    prep_failed: set[str] = set()

    entered_after_start = datetime.now(IST) >= times.start
    if entered_after_start:
        catchup_deadline = times.stop - timedelta(minutes=MIN_REMAINING_SESSION_MINUTES)
    else:
        catchup_deadline = min(
            times.start + timedelta(minutes=NORMAL_CATCHUP_MINUTES),
            times.stop - timedelta(minutes=MIN_REMAINING_SESSION_MINUTES),
        )

    while datetime.now(IST) < times.start:
        check_operator_stop()
        harvest_futures(prep_futures, prepared, prep_failed, f"{direction} preparation")
        update_session_state(
            state,
            day,
            direction,
            f"preparing_{direction}",
            prepared,
            active,
        )
        remaining = (times.start - datetime.now(IST)).total_seconds()
        if remaining <= START_GUARD_SECONDS:
            log(
                f"{direction}: entering {START_GUARD_SECONDS}s start guard with "
                f"prepared={sorted(prepared)}; slow pairs will catch up separately"
            )
            sleep_until(times.start)
            break
        STOP_REQUESTED.wait(min(PREPARE_POLL_SECONDS, max(0.1, remaining)))

    actual_trigger = datetime.now(IST)
    log(
        f"{direction.capitalize()} start boundary reached at {actual_trigger.isoformat()} "
        f"(skew {(actual_trigger - times.start).total_seconds():+.1f}s); "
        f"ready pairs={sorted(prepared)}, recovered active={sorted(active)}"
    )

    start_executor = concurrent.futures.ThreadPoolExecutor(max_workers=START_MAX_WORKERS)
    start_futures: dict[str, concurrent.futures.Future[Any]] = {
        pair_id: start_executor.submit(start_power_pair, pair_id, direction, target_kw)
        for pair_id in sorted(prepared - active)
    }
    started: set[str] = set(active)
    start_failed: set[str] = set()
    handled_start_failures: set[str] = set()
    submitted_for_start: set[str] = set(start_futures)
    status_errors: dict[str, int] = {pair_id: 0 for pair_id in PAIR_IDS}
    power_violations: dict[str, int] = {pair_id: 0 for pair_id in PAIR_IDS}

    update_session_state(state, day, direction, direction, prepared, started)

    while datetime.now(IST) < times.stop:
        check_operator_stop()
        require_storage_ready()

        harvest_futures(prep_futures, prepared, prep_failed, f"late {direction} preparation")
        now = datetime.now(IST)
        if now <= catchup_deadline:
            for pair_id in sorted(prepared - submitted_for_start - started):
                if pair_id in prep_failed:
                    continue
                submitted_for_start.add(pair_id)
                start_futures[pair_id] = start_executor.submit(
                    start_power_pair,
                    pair_id,
                    direction,
                    target_kw,
                )
                log(f"P{PAIR_NUMBER[pair_id]}: submitted for late {direction} catch-up")

        harvest_futures(start_futures, started, start_failed, f"{direction} power start")

        for pair_id in sorted(start_failed - handled_start_failures):
            handled_start_failures.add(pair_id)
            if pair_id in started:
                continue
            if safe_stop_pair(pair_id, f"{direction} start failure"):
                prepared.discard(pair_id)

        remaining = (times.stop - now).total_seconds()
        if remaining <= STOP_GUARD_SECONDS:
            log(
                f"{direction}: entering {STOP_GUARD_SECONDS}s stop guard; "
                "no further monitor request will cross the power-window boundary"
            )
            sleep_until(times.stop)
            break

        try:
            snapshots = get_all_pair_snapshots()
        except Exception as error:
            log(f"Session-wide cached status warning: {error}")
            for pair_id in started:
                status_errors[pair_id] += 1
            snapshots = {}

        to_stop: dict[str, str] = {}
        for pair_id in list(started):
            snapshot = snapshots.get(pair_id)
            if snapshot is None:
                if status_errors[pair_id] >= STATUS_ERROR_LIMIT:
                    to_stop[pair_id] = "cached status/SOC unavailable repeatedly"
                continue
            print_pair_snapshot(snapshot)
            status_errors[pair_id] = 0
            violation = pair_violation(snapshot, direction, target_kw)
            if violation is None:
                power_violations[pair_id] = 0
                continue
            immediate = (
                snapshot.soc >= CHARGE_STOP_SOC
                if direction == "charge"
                else snapshot.soc <= MIN_DISCHARGE_SOC
            ) or has_fault(snapshot.summary) or not bms_connected(snapshot.summary)
            if immediate:
                to_stop[pair_id] = violation
            else:
                power_violations[pair_id] += 1
                if power_violations[pair_id] >= POWER_VIOLATION_LIMIT:
                    to_stop[pair_id] = violation

        if to_stop:
            stop_results = run_parallel(
                f"{direction} early pair removal",
                to_stop,
                lambda pair_id: early_stop_pair(pair_id, to_stop[pair_id]),
                2,
            )
            for pair_id, (ok, value) in stop_results.items():
                if ok and value:
                    started.discard(pair_id)
                    prepared.discard(pair_id)
                else:
                    log(f"CRITICAL: P{PAIR_NUMBER[pair_id]} early safe-stop unverified")

        update_session_state(state, day, direction, direction, prepared, started)
        wait_seconds = min(
            MONITOR_POLL_SECONDS,
            max(0.1, (times.stop - datetime.now(IST)).total_seconds()),
        )
        STOP_REQUESTED.wait(wait_seconds)

    SESSION_STOPPING.set()
    log(f"{direction.capitalize()} power-window stop boundary: {times.stop.isoformat()}")
    if not backend_safe_stop_all(f"scheduled {direction} stop at {times.stop.isoformat()}"):
        raise RuntimeError(f"Scheduled {direction} safe-stop could not be verified")

    prep_executor.shutdown(wait=False, cancel_futures=True)
    start_executor.shutdown(wait=False, cancel_futures=True)
    mark_session_complete(state, day, direction)
    SESSION_STOPPING.clear()


def needs_safe_stop() -> bool:
    try:
        snapshots = get_all_pair_snapshots()
    except Exception as error:
        log(f"Unable to determine hardware state before final protection: {error}")
        return HARDWARE_TOUCHED
    for snapshot in snapshots.values():
        summary = snapshot.summary
        if (
            abs(number(summary, "pcs_power_setpoint_kw")) > 0.5
            or abs(number(summary, "pcs_actual_power_kw")) > 1.0
            or integer(summary, "pcs_operating_state") != 1
            or not bms_is_open(summary)
        ):
            return True
    return False


def validate_live_read_only() -> None:
    validate_configuration()
    login()
    validate_backend_capabilities()
    health = api_json("GET", "/api/health", timeout=60)
    log(
        f"Backend health={health.get('status')}, "
        f"assets_online={health.get('assets_online')}/{health.get('assets_total')}"
    )
    snapshots = get_all_pair_snapshots()
    for snapshot in snapshots.values():
        print_pair_snapshot(snapshot)
    log("Read-only validation passed for all four pairs; no control write was sent")


def print_schedule() -> None:
    for day in SCHEDULE_DATES:
        charge = session_times(day, "charge")
        discharge = session_times(day, "discharge")
        print(
            f"{day}: charge prepare {charge.prepare:%H:%M}, "
            f"power {charge.start:%H:%M}-{charge.stop:%H:%M} at {CHARGE_KW:.1f} kW/pair; "
            f"discharge prepare {discharge.prepare:%H:%M}, "
            f"power {discharge.start:%H:%M}-{discharge.stop:%H:%M} at {DISCHARGE_KW:.1f} kW/pair"
        )


def main() -> None:
    validate_configuration()
    acquire_process_lock()
    login()
    validate_backend_capabilities()
    state = load_state()

    log(
        "Seven-day backend-V3 scheduler armed: "
        f"charge {CHARGE_START_TIME}-{CHARGE_STOP_TIME} at {CHARGE_KW:.1f} kW/pair; "
        f"discharge {DISCHARGE_START_TIME}-{DISCHARGE_STOP_TIME} "
        f"at {DISCHARGE_KW:.1f} kW/pair"
    )

    for day in SCHEDULE_DATES:
        run_session(day, "charge", state)
        run_session(day, "discharge", state)

    state.update(
        {
            "phase": "complete",
            "current_session": None,
            "prepared_pairs": [],
            "active_pairs": [],
            "completed": True,
        }
    )
    save_state(state)
    log("All seven daily charge/discharge schedules completed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seven-day four-pair BESS scheduler for Kinetics Gateway V3"
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate configuration and cached live status without control writes",
    )
    parser.add_argument(
        "--print-schedule",
        action="store_true",
        help="Print the resolved seven-day IST schedule and exit",
    )
    parser.add_argument(
        "--safe-stop-now",
        action="store_true",
        help="Use the backend to zero and safe-stop all four pairs immediately",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    exit_code = 0
    try:
        if arguments.print_schedule:
            validate_configuration()
            print_schedule()
        elif arguments.validate_only:
            acquire_process_lock()
            validate_live_read_only()
        elif arguments.safe_stop_now:
            acquire_process_lock()
            login()
            if not backend_safe_stop_all("manual --safe-stop-now"):
                raise RuntimeError("Manual all-pair safe-stop was not fully verified")
        else:
            main()
    except OperatorStop as error:
        log(str(error))
        exit_code = 0
    except Exception as error:
        log(f"SUPERVISOR ERROR: {error}")
        exit_code = 1
    finally:
        if not arguments.print_schedule and current_token() is not None:
            if STOP_REQUESTED.is_set() or exit_code != 0:
                try:
                    if needs_safe_stop() and not backend_safe_stop_all(
                        "service exit/final protection"
                    ):
                        exit_code = 2
                except Exception as error:
                    log(f"CRITICAL: final protection failed: {error}")
                    exit_code = 2
    raise SystemExit(exit_code)
