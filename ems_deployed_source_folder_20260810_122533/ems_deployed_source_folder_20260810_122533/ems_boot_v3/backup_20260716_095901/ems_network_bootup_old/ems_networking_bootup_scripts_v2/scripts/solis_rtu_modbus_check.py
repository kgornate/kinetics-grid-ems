#!/usr/bin/env python3
"""Read-only Solis Modbus RTU probe used by EMS boot scripts.

It does not write anything. It only tries a few safe input-register reads so the
field team can confirm that the USB-RS485 wiring, baudrate and unit id are correct.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

try:
    try:
        from pymodbus.client import ModbusSerialClient
    except Exception:  # pymodbus 2.x
        from pymodbus.client.sync import ModbusSerialClient  # type: ignore
except Exception as exc:
    print(json.dumps({
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": "solis_rtu_probe_failed",
        "error": f"pymodbus import failed: {exc}",
    }, indent=2))
    sys.exit(3)


def make_client(args: argparse.Namespace):
    kwargs = dict(
        port=args.port,
        baudrate=args.baudrate,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=args.timeout,
    )
    try:
        return ModbusSerialClient(**kwargs)
    except TypeError:
        return ModbusSerialClient(method="rtu", **kwargs)


def try_modbus_call(calls):
    last_exc = None
    for call in calls:
        try:
            return call()
        except TypeError as exc:
            last_exc = exc
            continue
    if last_exc:
        raise last_exc
    raise RuntimeError("no compatible pymodbus call signature")


def read_input(client, address: int, count: int, unit_id: int):
    return try_modbus_call([
        lambda: client.read_input_registers(address=address, count=count, device_id=unit_id),
        lambda: client.read_input_registers(address, count=count, device_id=unit_id),
        lambda: client.read_input_registers(address=address, count=count, slave=unit_id),
        lambda: client.read_input_registers(address, count=count, slave=unit_id),
        lambda: client.read_input_registers(address=address, count=count, unit=unit_id),
        lambda: client.read_input_registers(address, count=count, unit=unit_id),
        lambda: client.read_input_registers(address, count, slave=unit_id),
        lambda: client.read_input_registers(address, count, unit=unit_id),
        lambda: client.read_input_registers(address, count),
    ])


def read_holding(client, address: int, count: int, unit_id: int):
    return try_modbus_call([
        lambda: client.read_holding_registers(address=address, count=count, device_id=unit_id),
        lambda: client.read_holding_registers(address, count=count, device_id=unit_id),
        lambda: client.read_holding_registers(address=address, count=count, slave=unit_id),
        lambda: client.read_holding_registers(address, count=count, slave=unit_id),
        lambda: client.read_holding_registers(address=address, count=count, unit=unit_id),
        lambda: client.read_holding_registers(address, count=count, unit=unit_id),
        lambda: client.read_holding_registers(address, count, slave=unit_id),
        lambda: client.read_holding_registers(address, count, unit=unit_id),
        lambda: client.read_holding_registers(address, count),
    ])


def regs_or_error(rr):
    if rr is None:
        return None, "no_response"
    if hasattr(rr, "isError") and rr.isError():
        return None, str(rr)
    regs = getattr(rr, "registers", None)
    if regs is None:
        return None, str(rr)
    return regs, None


def u32_be(regs):
    if len(regs) < 2:
        return None
    return (int(regs[0]) << 16) | int(regs[1])


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--port", required=True)
    p.add_argument("--baudrate", type=int, default=9600)
    p.add_argument("--unit-id", type=int, default=1)
    p.add_argument("--timeout", type=float, default=3.0)
    args = p.parse_args()

    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": "solis_rtu_read_only_probe",
        "port": args.port,
        "baudrate": args.baudrate,
        "unit_id": args.unit_id,
        "reads": {},
    }

    client = make_client(args)
    if not client.connect():
        result["online"] = False
        result["error"] = "serial_connect_failed"
        print(json.dumps(result, indent=2))
        return 2

    success = False
    # 35000 inverter type definition uses FC04 and no offset in datasheet.
    for name, fn, address, count, scale in [
        ("inverter_type_definition_35000", read_input, 35000, 1, None),
        # Operation information table uses -1 send-address offset.
        ("product_model_3000_send_2999", read_input, 2999, 1, None),
        ("active_power_3005_send_3004", read_input, 3004, 2, "u32_w"),
        ("inverter_status_3044_send_3043", read_input, 3043, 1, None),
        ("on_off_setting_3007_send_3006", read_holding, 3006, 1, None),
    ]:
        try:
            rr = fn(client, address, count, args.unit_id)
            regs, err = regs_or_error(rr)
            if err:
                result["reads"][name] = {"address": address, "ok": False, "error": err}
                continue
            entry = {"address": address, "ok": True, "raw_registers": regs}
            if scale == "u32_w":
                entry["value_w"] = u32_be(regs)
            elif regs:
                entry["value"] = int(regs[0])
            result["reads"][name] = entry
            success = True
        except Exception as exc:
            result["reads"][name] = {"address": address, "ok": False, "error": str(exc)}

    try:
        client.close()
    except Exception:
        pass

    result["online"] = success
    print(json.dumps(result, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
