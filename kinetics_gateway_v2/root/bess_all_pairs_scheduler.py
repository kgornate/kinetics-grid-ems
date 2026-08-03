#!/usr/bin/env python3

import json
import os
import signal
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

PAIRS = {
    1: 503,
    2: 504,
    3: 505,
    4: 506,
}

BMS_HOST = os.environ.get("BMS_HOST", "192.168.111.22")
SOURCE_IP = os.environ.get("BMS_SOURCE_IP", "192.168.111.2")
BAU_UNIT_ID = int(os.environ.get("BAU_UNIT_ID", "1"))
SOC_ADDRESS = int(os.environ.get("SOC_ADDRESS", "0x2004"), 0)
BAU_CONNECT_ADDRESS = int(os.environ.get("BAU_CONNECT_ADDRESS", "0x3001"), 0)

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000")
API_USER = os.environ["API_USER"]
API_PASS = os.environ["API_PASS"]

CHARGE_STOP_SOC = float(os.environ.get("CHARGE_STOP_SOC", "96.0"))
MIN_DISCHARGE_SOC = float(os.environ.get("MIN_DISCHARGE_SOC", "20.0"))
DISCHARGE_KW = float(os.environ.get("DISCHARGE_KW", "200.0"))
SITE_MAX_TOTAL_DISCHARGE_KW = float(
    os.environ.get("SITE_MAX_TOTAL_DISCHARGE_KW", "1000.0")
)
START_DELAY_MINUTES = int(os.environ.get("START_DELAY_MINUTES", "135"))
PREPARE_LEAD_MINUTES = int(os.environ.get("PREPARE_LEAD_MINUTES", "10"))
DISCHARGE_DURATION_MINUTES = int(
    os.environ.get("DISCHARGE_DURATION_MINUTES", "120")
)
SOC_POLL_SECONDS = int(os.environ.get("SOC_POLL_SECONDS", "20"))
DISCHARGE_POLL_SECONDS = int(
    os.environ.get("DISCHARGE_POLL_SECONDS", "10")
)

ARM_PHRASE = os.environ.get("ARM_PHRASE", "")
REQUIRED_ARM_PHRASE = "EXECUTE_ALL_4_PAIR_SCHEDULE"

PYTHON = "/opt/kinetics-gateway/venv/bin/python"
CLI = "/opt/kinetics-gateway/backend/tools/control_sequence_cli.py"
STATE_DIR = "/var/lib/bess-all-pairs-scheduler"
STATE_FILE = f"{STATE_DIR}/state.json"

TOKEN = None
SHUTDOWN_REQUESTED = False
CONTROL_ARMED = False
CYCLE_COMPLETED = False


def log(message):
    stamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S %Z")
    print(f"[{stamp}] {message}", flush=True)


def signal_handler(signum, frame):
    global SHUTDOWN_REQUESTED
    SHUTDOWN_REQUESTED = True
    log(f"Signal {signum} received; safe-stop requested")


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def validate_configuration():
    requested_total = DISCHARGE_KW * len(PAIRS)

    if ARM_PHRASE != REQUIRED_ARM_PHRASE:
        raise RuntimeError("ARM_PHRASE is incorrect; no hardware command sent")

    if not 0 < MIN_DISCHARGE_SOC < CHARGE_STOP_SOC <= 100:
        raise RuntimeError(
            "SOC thresholds invalid: require 0 < MIN_DISCHARGE_SOC "
            "< CHARGE_STOP_SOC <= 100"
        )

    if DISCHARGE_KW <= 0 or DISCHARGE_KW > 240:
        raise RuntimeError("DISCHARGE_KW must be greater than 0 and at most 240")

    if requested_total > SITE_MAX_TOTAL_DISCHARGE_KW:
        raise RuntimeError(
            f"Requested total {requested_total:.1f} kW exceeds site limit "
            f"{SITE_MAX_TOTAL_DISCHARGE_KW:.1f} kW"
        )

    if START_DELAY_MINUTES <= PREPARE_LEAD_MINUTES:
        raise RuntimeError(
            "START_DELAY_MINUTES must be greater than PREPARE_LEAD_MINUTES"
        )

    if DISCHARGE_DURATION_MINUTES <= 0:
        raise RuntimeError("DISCHARGE_DURATION_MINUTES must be positive")

    if not os.path.exists(PYTHON):
        raise RuntimeError(f"Python environment not found: {PYTHON}")

    if not os.path.exists(CLI):
        raise RuntimeError(f"Control CLI not found: {CLI}")

    log(
        f"Configuration valid: {len(PAIRS)} pairs x {DISCHARGE_KW:.1f} kW "
        f"= {requested_total:.1f} kW, site limit "
        f"{SITE_MAX_TOTAL_DISCHARGE_KW:.1f} kW"
    )


def save_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    temporary = f"{STATE_FILE}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)
    os.replace(temporary, STATE_FILE)


def load_or_create_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as handle:
            state = json.load(handle)
        log(f"Reusing persisted schedule from {STATE_FILE}")
        return state

    created_at = datetime.now(IST)
    target_start = created_at + timedelta(minutes=START_DELAY_MINUTES)
    prepare_at = target_start - timedelta(minutes=PREPARE_LEAD_MINUTES)

    state = {
        "created_at": created_at.isoformat(),
        "prepare_at": prepare_at.isoformat(),
        "target_start": target_start.isoformat(),
        "actual_discharge_start": None,
        "stop_at": None,
        "phase": "charge_cutoff_monitoring",
        "active_pairs": [],
        "completed": False,
    }
    save_state(state)
    return state


def parse_time(value):
    return datetime.fromisoformat(value).astimezone(IST)


def recv_exact(sock, count):
    data = b""
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise RuntimeError("Modbus TCP connection closed")
        data += chunk
    return data


def modbus_transaction(port, unit_id, pdu):
    transaction_id = int(time.time() * 1000) & 0xFFFF
    request = struct.pack(
        ">HHHB", transaction_id, 0, len(pdu) + 1, unit_id
    ) + pdu

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(4.0)
        sock.bind((SOURCE_IP, 0))
        sock.connect((BMS_HOST, port))
        sock.sendall(request)
        header = recv_exact(sock, 7)
        rx_tid, protocol, length, rx_unit = struct.unpack(">HHHB", header)
        body = recv_exact(sock, length - 1)

    if rx_tid != transaction_id:
        raise RuntimeError("Modbus transaction ID mismatch")
    if protocol != 0 or rx_unit != unit_id:
        raise RuntimeError("Invalid Modbus response header")
    if body[0] & 0x80:
        raise RuntimeError(f"Modbus exception code {body[1]}")
    return body


def read_input_registers(port, address, count):
    body = modbus_transaction(
        port, BAU_UNIT_ID, struct.pack(">BHH", 4, address, count)
    )
    if body[0] != 4:
        raise RuntimeError(f"Unexpected function code {body[0]}")
    byte_count = body[1]
    if byte_count != count * 2:
        raise RuntimeError(f"Unexpected byte count {byte_count}")
    return list(
        struct.unpack(">" + ("H" * count), body[2 : 2 + byte_count])
    )


def write_holding_register(port, address, value):
    body = modbus_transaction(
        port, BAU_UNIT_ID, struct.pack(">BHH", 6, address, value)
    )
    function, returned_address, returned_value = struct.unpack(">BHH", body)
    if (
        function != 6
        or returned_address != address
        or returned_value != value
    ):
        raise RuntimeError("Unexpected Modbus write response")
    log(f"Port {port}: wrote {value} to BAU 0x{address:04X}")


def read_soc(pair):
    raw = read_input_registers(PAIRS[pair], SOC_ADDRESS, 1)[0]
    return raw / 10.0


def login():
    global TOKEN
    payload = json.dumps({"username": API_USER, "password": API_PASS}).encode()
    request = urllib.request.Request(
        f"{BASE_URL}/api/auth/login",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        TOKEN = json.load(response)["access_token"]
    log("Gateway authentication successful")


def api_json(method, path, payload=None):
    global TOKEN
    if TOKEN is None:
        login()

    data = None if payload is None else json.dumps(payload).encode()

    for attempt in range(2):
        request = urllib.request.Request(
            f"{BASE_URL}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")
            if error.code == 401 and attempt == 0:
                login()
                continue
            raise RuntimeError(f"HTTP {error.code}: {detail}") from error

    raise RuntimeError("API request failed")


def get_status(pair):
    latest = None
    for _ in range(10):
        latest = api_json(
            "GET", f"/api/control-sequence/pair_{pair}/status?fresh=true"
        )
        refresh = latest.get("refresh") or {}
        if refresh.get("source") != "cached_while_live_refresh_busy":
            break
        time.sleep(1)

    summary = latest.get("summary") if isinstance(latest, dict) else None
    if not isinstance(summary, dict):
        raise RuntimeError(f"Pair {pair}: top-level live summary missing")
    return latest, summary


def blockers(summary):
    return summary.get("blockers") or {}


def has_fault(summary):
    block = blockers(summary)
    return any(
        [
            bool(summary.get("pcs_fault_shutdown")),
            bool(block.get("system_fault")),
            bool(block.get("documented_critical_fault")),
            bool(block.get("emergency_stop_fault")),
        ]
    )


def number(summary, key):
    return float(summary.get(key) or 0.0)


def integer(summary, key):
    return int(float(summary.get(key) or 0))


def print_pair_status(pair, summary, soc):
    log(
        f"P{pair}: SOC={soc:.1f}% PRE={integer(summary, 'precharge_state')} "
        f"CONTACTORS={bool(summary.get('positive_contactor_closed'))}/"
        f"{bool(summary.get('negative_contactor_closed'))} "
        f"PCS={integer(summary, 'pcs_operating_state')} "
        f"SET={number(summary, 'pcs_power_setpoint_kw'):.1f} kW "
        f"ACT={number(summary, 'pcs_actual_power_kw'):.1f} kW "
        f"DSG_LIMIT={number(summary, 'rack_discharge_current_limit_a'):.1f} A "
        f"FAULT={has_fault(summary)}"
    )


def power_is_zero(summary):
    return (
        abs(number(summary, "pcs_power_setpoint_kw")) <= 0.5
        and abs(number(summary, "pcs_actual_power_kw")) <= 1.0
    )


def pcs_is_stopped(summary):
    return (
        integer(summary, "pcs_operating_state") == 1
        and power_is_zero(summary)
        and not bool(summary.get("pcs_fault_shutdown"))
    )


def bms_is_open(summary):
    return (
        integer(summary, "precharge_state") == 0
        and not bool(summary.get("positive_contactor_closed"))
        and not bool(summary.get("negative_contactor_closed"))
    )


def fully_stopped(summary):
    return pcs_is_stopped(summary) and bms_is_open(summary)


def bms_is_ready(summary):
    rack_voltage = number(summary, "rack_voltage_v")
    pcs_input = number(summary, "pcs_battery_voltage_v")
    voltage_match = (
        1100.0 <= rack_voltage <= 1500.0
        and 1100.0 <= pcs_input <= 1500.0
        and abs(rack_voltage - pcs_input) <= 50.0
    )
    return (
        integer(summary, "precharge_state") == 3
        and bool(summary.get("positive_contactor_closed"))
        and bool(summary.get("negative_contactor_closed"))
        and number(summary, "rack_charge_current_limit_a") > 0
        and number(summary, "rack_discharge_current_limit_a") > 0
        and voltage_match
        and not has_fault(summary)
    )


def pcs_is_ready_zero(summary):
    return (
        integer(summary, "pcs_operating_state") in (32, 80)
        and bms_is_ready(summary)
        and power_is_zero(summary)
        and not has_fault(summary)
    )


def wait_for(pair, predicate, description, timeout_seconds):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if SHUTDOWN_REQUESTED:
            raise InterruptedError("Operator safe-stop requested")
        _, summary = get_status(pair)
        soc = read_soc(pair)
        print_pair_status(pair, summary, soc)
        if predicate(summary):
            log(f"P{pair}: verified {description}")
            return summary
        time.sleep(3)
    raise TimeoutError(f"P{pair}: timed out waiting for {description}")


def command_zero(pair):
    api_json(
        "POST",
        f"/api/control/pcs_{pair}/active_power_setpoint",
        {"value": 0},
    )


def command_pcs_stop(pair):
    api_json(
        "POST",
        f"/api/control/pcs_{pair}/remote_on_off_command",
        {"value": 255},
    )


def safe_stop(pair):
    log(f"P{pair}: safe-stop starting")
    try:
        _, current = get_status(pair)
        if fully_stopped(current):
            log(f"P{pair}: already safely stopped and disconnected")
            return
    except Exception as error:
        log(f"P{pair}: initial stop-state read warning: {error}")

    command_zero(pair)
    wait_for(pair, power_is_zero, "zero active power", 180)

    command_pcs_stop(pair)
    wait_for(pair, pcs_is_stopped, "PCS stopped", 180)

    write_holding_register(PAIRS[pair], BAU_CONNECT_ADDRESS, 2)
    wait_for(pair, fully_stopped, "PCS stopped and BMS contactors open", 180)
    log(f"P{pair}: safe-stop complete")


def run_cli(command, pair, tolerate_nonzero=False):
    arguments = [
        PYTHON,
        CLI,
        command,
        "--pair-id",
        f"pair_{pair}",
        "--confirmation",
        "EXECUTE_STAGE_WRITE",
    ]
    result = subprocess.run(
        arguments,
        cwd="/opt/kinetics-gateway/backend",
        text=True,
        capture_output=True,
        timeout=240,
    )

    if result.stdout:
        log(f"P{pair} {command} stdout:\n{result.stdout[-2000:]}")
    if result.stderr:
        log(f"P{pair} {command} stderr:\n{result.stderr[-2000:]}")

    if result.returncode != 0 and not tolerate_nonzero:
        raise RuntimeError(
            f"P{pair}: {command} failed with return code {result.returncode}"
        )


def prepare_pair(pair):
    log(f"P{pair}: preparing for scheduled discharge at zero power")
    safe_stop(pair)

    write_holding_register(PAIRS[pair], BAU_CONNECT_ADDRESS, 1)
    wait_for(pair, bms_is_ready, "BMS precharge/contactors ready", 240)

    run_cli("configure-pcs", pair, tolerate_nonzero=False)
    run_cli("start-pcs", pair, tolerate_nonzero=True)
    wait_for(pair, pcs_is_ready_zero, "PCS ready at zero power", 300)
    log(f"P{pair}: preparation complete")


def command_discharge(pair):
    soc = read_soc(pair)
    if soc <= MIN_DISCHARGE_SOC:
        raise RuntimeError(
            f"SOC {soc:.1f}% is at or below minimum "
            f"{MIN_DISCHARGE_SOC:.1f}%"
        )

    _, summary = get_status(pair)
    if not pcs_is_ready_zero(summary):
        raise RuntimeError("PCS/BMS is not ready at zero power")

    precheck = api_json(
        "POST",
        f"/api/control-sequence/pair_{pair}/precheck",
        {"direction": "discharge", "power_kw": DISCHARGE_KW},
    )
    if not precheck.get("ok"):
        raise RuntimeError(
            "Discharge precheck failed: "
            + json.dumps(precheck.get("checks", {}), sort_keys=True)
        )

    response = api_json(
        "POST",
        f"/api/control-sequence/pair_{pair}/set-power",
        {
            "direction": "discharge",
            "power_kw": DISCHARGE_KW,
            "confirmation": "EXECUTE_STAGE_WRITE",
        },
    )
    if not response.get("ok"):
        raise RuntimeError("Discharge command was not accepted")

    log(f"P{pair}: +{DISCHARGE_KW:.1f} kW discharge accepted")


def sleep_until(target):
    while True:
        if SHUTDOWN_REQUESTED:
            raise InterruptedError("Operator safe-stop requested")
        remaining = (target - datetime.now(IST)).total_seconds()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 10))


def monitor_charge_cutoff(prepare_at):
    log(
        f"SOC cutoff monitoring active until {prepare_at.isoformat()}; "
        f"each pair stops at SOC >= {CHARGE_STOP_SOC:.1f}%"
    )
    last_summary_log = 0.0

    while datetime.now(IST) < prepare_at:
        if SHUTDOWN_REQUESTED:
            raise InterruptedError("Operator safe-stop requested")

        for pair in PAIRS:
            try:
                soc = read_soc(pair)
                _, summary = get_status(pair)
                if time.monotonic() - last_summary_log > 60:
                    print_pair_status(pair, summary, soc)

                if soc >= CHARGE_STOP_SOC and not fully_stopped(summary):
                    log(
                        f"P{pair}: SOC {soc:.1f}% reached cutoff "
                        f"{CHARGE_STOP_SOC:.1f}%; stopping"
                    )
                    safe_stop(pair)

            except Exception as error:
                log(f"P{pair}: cutoff-monitor warning: {error}")

        if time.monotonic() - last_summary_log > 60:
            last_summary_log = time.monotonic()

        time.sleep(SOC_POLL_SECONDS)


def prepare_all_pairs(state):
    prepared = []
    state["phase"] = "preparing"
    save_state(state)

    for pair in PAIRS:
        if SHUTDOWN_REQUESTED:
            raise InterruptedError("Operator safe-stop requested")
        try:
            prepare_pair(pair)
            prepared.append(pair)
        except Exception as error:
            log(f"P{pair}: preparation failed; pair will be skipped: {error}")
            try:
                safe_stop(pair)
            except Exception as stop_error:
                log(f"P{pair}: safe-stop after preparation failure failed: {stop_error}")

    return prepared


def start_discharge(prepared, state):
    target_start = parse_time(state["target_start"])
    sleep_until(target_start)
    log(f"Scheduled discharge trigger reached: {target_start.isoformat()}")

    active = []
    for pair in prepared:
        try:
            command_discharge(pair)
            active.append(pair)
        except Exception as error:
            log(f"P{pair}: discharge not started: {error}")
            try:
                safe_stop(pair)
            except Exception as stop_error:
                log(f"P{pair}: safe-stop failure: {stop_error}")

    actual_start = datetime.now(IST)
    stop_at = actual_start + timedelta(minutes=DISCHARGE_DURATION_MINUTES)
    state["phase"] = "discharging"
    state["active_pairs"] = active
    state["actual_discharge_start"] = actual_start.isoformat()
    state["stop_at"] = stop_at.isoformat()
    save_state(state)

    log(
        f"Discharge batch active pairs={active}; final stop scheduled for "
        f"{stop_at.isoformat()}"
    )
    return active, stop_at


def monitor_discharge(active, stop_at):
    active = set(active)
    direction_grace_deadline = time.monotonic() + 60

    while datetime.now(IST) < stop_at and active:
        if SHUTDOWN_REQUESTED:
            raise InterruptedError("Operator safe-stop requested")

        for pair in list(active):
            try:
                soc = read_soc(pair)
                _, summary = get_status(pair)
                print_pair_status(pair, summary, soc)

                stop_reason = None
                actual = number(summary, "pcs_actual_power_kw")

                if soc <= MIN_DISCHARGE_SOC:
                    stop_reason = (
                        f"SOC {soc:.1f}% reached minimum "
                        f"{MIN_DISCHARGE_SOC:.1f}%"
                    )
                elif has_fault(summary):
                    stop_reason = "PCS/BMS/system fault active"
                elif number(summary, "rack_discharge_current_limit_a") <= 0:
                    stop_reason = "BMS discharge current limit became zero"
                elif not bms_is_ready(summary):
                    stop_reason = "BMS contactor/precharge readiness lost"
                elif time.monotonic() > direction_grace_deadline and actual < -1.0:
                    stop_reason = "Power direction is charging, not discharging"

                if stop_reason:
                    log(f"P{pair}: early safe-stop: {stop_reason}")
                    safe_stop(pair)
                    active.remove(pair)

            except Exception as error:
                log(f"P{pair}: discharge-monitor error; stopping pair: {error}")
                try:
                    safe_stop(pair)
                finally:
                    active.discard(pair)

        time.sleep(DISCHARGE_POLL_SECONDS)

    if active:
        log(f"Two-hour discharge duration reached; stopping pairs {sorted(active)}")


def stop_all_best_effort():
    log("Final safe-stop of all four pairs starting")
    for pair in PAIRS:
        try:
            safe_stop(pair)
        except Exception as error:
            log(f"P{pair}: FINAL SAFE-STOP ERROR: {error}")
    log("Final safe-stop pass finished")


def main():
    global CONTROL_ARMED, CYCLE_COMPLETED

    validate_configuration()
    state = load_or_create_state()

    log(f"Prepare time: {state['prepare_at']}")
    log(f"Target discharge trigger: {state['target_start']}")
    log(
        f"Discharge duration after commands are issued: "
        f"{DISCHARGE_DURATION_MINUTES} minutes"
    )

    if state.get("completed"):
        log("State file says schedule is already completed; exiting")
        return

    login()
    CONTROL_ARMED = True

    if state.get("phase") == "discharging" and state.get("stop_at"):
        active = state.get("active_pairs") or list(PAIRS)
        stop_at = parse_time(state["stop_at"])
        if datetime.now(IST) < stop_at:
            log("Resuming discharge monitoring from persisted state")
            monitor_discharge(active, stop_at)
        stop_all_best_effort()
        state["phase"] = "complete"
        state["completed"] = True
        save_state(state)
        CYCLE_COMPLETED = True
        return

    prepare_at = parse_time(state["prepare_at"])
    target_start = parse_time(state["target_start"])

    if datetime.now(IST) >= target_start:
        raise RuntimeError(
            "Target start time has already passed before preparation; refusing "
            "to begin an unexpected discharge"
        )

    monitor_charge_cutoff(prepare_at)
    prepared = prepare_all_pairs(state)

    if not prepared:
        raise RuntimeError("No pair completed preparation; no discharge started")

    active, stop_at = start_discharge(prepared, state)

    if not active:
        raise RuntimeError("No pair accepted the discharge command")

    monitor_discharge(active, stop_at)
    stop_all_best_effort()

    state["phase"] = "complete"
    state["completed"] = True
    save_state(state)
    CYCLE_COMPLETED = True
    log("Scheduled cycle completed")


if __name__ == "__main__":
    exit_code = 0
    try:
        main()
    except InterruptedError as error:
        log(str(error))
        exit_code = 1
    except Exception as error:
        log(f"SUPERVISOR ERROR: {error}")
        exit_code = 1
    finally:
        if CONTROL_ARMED and not CYCLE_COMPLETED:
            stop_all_best_effort()
    raise SystemExit(exit_code)
