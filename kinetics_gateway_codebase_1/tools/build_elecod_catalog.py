#!/usr/bin/env python3
"""Build a Kinetics-compatible Elecod Monet-AC V2.7.0 protocol catalog.

The generator extracts tables directly from the vendor PDF with pdfplumber and
adds only explicit, traceable normalization needed by the frozen gateway
architecture (data types, register widths, critical scales/enums, alarm/status
bitfields). Ambiguous operational semantics are kept as commissioning notes.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import pdfplumber


CRITICAL_KEYS = {
    1050: "grid_voltage_ab",
    1051: "grid_voltage_bc",
    1052: "grid_voltage_ca",
    1053: "grid_current_a",
    1054: "grid_current_b",
    1055: "grid_current_c",
    1056: "grid_frequency_a",
    1057: "grid_frequency_b",
    1058: "grid_frequency_c",
    1059: "total_power_factor",
    1060: "total_active_power",
    1061: "total_reactive_power",
    1062: "total_apparent_power",
    1063: "dc_voltage",
    1064: "dc_current",
    1065: "dc_power",
    1066: "dc_bus_voltage",
    1067: "positive_bus_voltage",
    1068: "negative_bus_voltage",
    1073: "leakage_current",
    1074: "power_tube_temperature",
    1075: "balance_bridge_temperature",
    1076: "ambient_temperature",
    1077: "converter_efficiency",
    1105: "total_charge_energy_since_powerup",
    1107: "total_discharge_energy_since_powerup",
    2050: "alarm_word_1",
    2051: "alarm_word_2",
    2052: "alarm_word_3",
    2053: "alarm_word_4",
    2054: "alarm_word_5",
    2055: "alarm_word_6",
    2056: "alarm_word_7",
    2057: "status_word",
    3050: "active_power_setpoint_percent",
    3051: "reactive_power_setpoint_percent",
    3052: "power_factor_setpoint",
    3134: "battery_type",
    3135: "battery_undervoltage_protection",
    3136: "battery_undervoltage_recovery",
    3137: "battery_overvoltage_protection",
    3138: "battery_overvoltage_recovery",
    3139: "battery_charge_current_limit",
    3140: "battery_discharge_current_limit",
    3143: "dc_bus_voltage_reference",
    3145: "dc_bus_overvoltage_point",
    3146: "rated_power_kw",
    3147: "rated_phase_voltage",
    3148: "rated_frequency",
    3149: "grid_side_wiring",
    3152: "reactive_mode",
    3157: "grid_mode_command",
    3158: "grid_connected_switching",
    3159: "on_grid_control_mode",
    3160: "off_grid_control_mode",
    3166: "inertia_time_constant",
    3167: "damping_factor",
    3168: "primary_frequency_regulation_enable",
    3169: "primary_voltage_regulation_enable",
    3182: "module_address",
    3183: "cabinet_address",
    3184: "battery_soc_input",
    3185: "battery_soc_sag_enable",
    3305: "bms_enable",
    3306: "bms_comm_fault_shutdown_enable",
    3307: "ip_address_1",
    3308: "ip_address_2",
    3309: "ip_address_3",
    3310: "ip_address_4",
    3311: "tcp_port",
    3326: "communication_failure_confirmation_time",
    3328: "bms_protocol",
    3329: "automatic_power_on",
    3350: "active_power_control_mode",
    5050: "power_on_off_command",
    5051: "standby_shutdown_command",
}

ENUMS: dict[int, dict[str, str]] = {
    3134: {"0": "Lithium", "1": "Lead acid", "2": "PV", "3": "DC bus"},
    3149: {"0": "3-wire", "1": "4-wire"},
    3152: {"0": "Non-adjustable", "1": "Power factor", "2": "Reactive power"},
    3157: {"0": "On-grid", "1": "Off-grid"},
    3158: {"0": "Command trigger", "1": "Grid trigger"},
    3159: {"0": "PQ", "1": "MPPT", "2": "CV", "3": "VSG"},
    3160: {"0": "VSG", "1": "VF"},
    3168: {"0": "Disabled", "1": "Enabled"},
    3169: {"0": "Disabled", "1": "Enabled"},
    3185: {"0": "Disabled", "1": "Enabled"},
    3305: {"0": "Disabled", "1": "Enabled"},
    3306: {"0": "Disabled", "1": "Enabled"},
    3329: {"0": "Disabled", "1": "Enabled"},
    3350: {"0": "Fixed slope", "1": "Fixed frequency"},
    5050: {"0": "Power off", "65280": "Power on"},
    5051: {"0": "Shutdown", "65280": "Standby"},
}

# Explicit scales for the control-critical fields and telemetry values where the
# PDF states a raw-to-engineering conversion. Remaining configuration points
# retain their raw range text and are not silently assigned a scale.
SCALE_OVERRIDES = {
    3050: 0.1, 3051: 0.1, 3052: 0.001,
    3135: 0.1, 3136: 0.1, 3137: 0.1, 3138: 0.1,
    3139: 0.1, 3140: 0.1, 3141: 0.1, 3142: 0.1,
    3143: 0.1, 3145: 0.1, 3146: 0.1,
    3166: 0.01, 3167: 0.1,
    3184: 0.1,
}

UNIT_OVERRIDES = {
    3050: "%", 3051: "%", 3052: None, 3062: "%/s",
    3135: "V", 3136: "V", 3137: "V", 3138: "V", 3139: "A", 3140: "A",
    3141: "V", 3142: "V", 3143: "V", 3144: "kΩ", 3145: "V", 3146: "kW",
    3147: "V", 3148: "Hz", 3166: "s", 3171: "Hz", 3184: "%",
    3187: "%/s", 3188: "ms", 3326: "s", 3355: "s", 3356: "ms",
}


SPECIAL_CONTINUATIONS = {
    3095: ("Grid over-voltage five-level protection time", "0~3600000 ms (default 20)"),
    3136: ("Battery under-voltage recovery point", None),
    3172: ("FM active upper limit", "0~1000 (0%~200%) (default 1000)"),
    3217: ("Discharge P-U Voltage Point 2", "1000~1500 (100%~150%) (default 1110)"),
    3234: ("Q-U power factor setpoint", "0~1000 (0~1) (default 400)"),
    3251: ("Cumulative grid overvoltage point", "105~150 (105%~150%) (default 110)"),
    3267: ("Active power point 5 on the Q-P curve", "-1200~1200 (-120%~120%) (default 1000)"),
    3282: ("High-side short-circuit recovery", "100~150 (100%~150%) (default 108)"),
    3296: ("Charging P-U active power limit 4", "-1200~0 (-120%~0%) (default 0)"),
}


def clean(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("\u3000", " ")).strip()


def slug(text: str) -> str:
    text = re.sub(r"([a-z])([A-Z])", r"\1_\2", text)
    text = text.replace("&", " and ").replace("%", " percent ").replace("℃", " temperature ")
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()) or "unnamed"


def dtype(raw: str, byte_count: int) -> str:
    value = clean(raw).upper()
    if "UINT32" in value:
        return "U32"
    if "INT32" in value:
        return "S32"
    if "UINT16" in value:
        return "U16"
    if "INT16" in value:
        return "S16"
    if byte_count == 4:
        return "U32"
    return "U16"


def infer_scale_from_corresponds(value_text: str) -> float | None:
    compact = value_text.replace(" ", "")
    match = re.search(r"(-?\d+(?:\.\d+)?)correspondsto(-?\d+(?:\.\d+)?)", compact, flags=re.I)
    if not match:
        return None
    raw = float(match.group(1))
    engineering = float(match.group(2))
    if raw == 0:
        return None
    ratio = engineering / raw
    return round(ratio, 9)


def unit_from_value(value_text: str) -> str | None:
    text = value_text or ""
    for pattern, unit in [
        (r"kvar", "kvar"), (r"kVA", "kVA"), (r"kWh", "kWh"), (r"kW", "kW"),
        (r"Hz", "Hz"), (r"kΩ", "kΩ"), (r"℃", "℃"), (r"%", "%"),
        (r"(?<=\d)V(?:\b|$)", "V"), (r"(?<=\d)A(?:\b|$)", "A"),
        (r"(?<=\d)ms(?:\b|$)", "ms"), (r"(?<=\d)min(?:\b|$)", "min"),
        (r"(?<=\d)s(?:\b|$)", "s"),
    ]:
        if re.search(pattern, text):
            return unit
    return None


def key_for(address: int, item: str) -> str:
    if address in CRITICAL_KEYS:
        return CRITICAL_KEYS[address]
    return slug(item) if item else f"reserved_{address}"


def category_for(address: int) -> str:
    if 1000 <= address <= 1044:
        return "identity"
    if 1050 <= address <= 1108:
        return "telemetry"
    if 2050 <= address <= 2056:
        return "alarm"
    if address == 2057:
        return "status"
    if 3050 <= address <= 3300:
        return "control_parameter"
    if 3301 <= address <= 3335:
        return "communication_parameter"
    if 3350 <= address <= 3360:
        return "control_parameter_2"
    if 1500 <= address <= 1505:
        return "rtc"
    if 5050 <= address <= 5051:
        return "remote_control"
    return "other"


def poll_class(address: int, reserved: bool) -> str:
    if reserved:
        return "disabled"
    if 2050 <= address <= 2057:
        return "fast"
    if address in {1060, 1061, 1063, 1064, 1065, 1066, 1074, 1076, 1077}:
        return "fast"
    if 1050 <= address <= 1108:
        return "normal"
    if 1000 <= address <= 1044:
        return "slow"
    return "disabled"


def parse_bit_tables(pdf: pdfplumber.PDF) -> dict[int, list[dict[str, Any]]]:
    bitfields: dict[int, list[dict[str, Any]]] = {}
    current_id: int | None = None
    for page_index in range(16, 22):  # PDF pages 17..22
        for table in pdf.pages[page_index].extract_tables():
            for row in table:
                if len(row) < 4:
                    continue
                id_text, bit_text, item, value = row[:4]
                id_clean = clean(id_text)
                if re.fullmatch(r"20(?:5[0-7])", id_clean):
                    current_id = int(id_clean)
                bit_match = re.search(r"Bit\s*(\d+)", clean(bit_text), flags=re.I)
                if current_id is None or not bit_match:
                    continue
                item_clean = clean(item)
                if not item_clean:
                    continue
                bit = int(bit_match.group(1))
                bitfields.setdefault(current_id, []).append({
                    "bit": bit,
                    "key": slug(item_clean),
                    "name_en": item_clean,
                    "value_text": clean(value),
                })
    return bitfields


def row_to_point(address: int, byte_count: int, item: str, value: str, dtype_text: str, fmt: str, *, access: str) -> dict[str, Any]:
    category = category_for(address)
    reserved = "reserved" in item.lower() or item.lower() == "reserve" or not item
    data_type = dtype(dtype_text, byte_count)
    register_count = 2 if byte_count == 4 or data_type in {"U32", "S32"} else 1
    scale = SCALE_OVERRIDES.get(address)
    if scale is None and category == "telemetry":
        scale = infer_scale_from_corresponds(value)
    key = key_for(address, item)
    write_function: int | None = None
    read_function = 3
    readback_enabled = True
    if category in {"identity", "telemetry", "alarm", "status"}:
        access = "R"
        read_function = 3  # Vendor permits FC03 or FC04; default FC03, configurable by catalog override.
    elif category in {"control_parameter", "communication_parameter", "control_parameter_2"}:
        access = "RW"
        read_function = 3
        write_function = 16 if register_count > 1 else 6
    elif category == "rtc":
        access = "RW"
        read_function = 3
        write_function = 16
    elif category == "remote_control":
        access = "W"
        read_function = 3
        # V2.7.0 revision history says FC05 was removed from remote adjustment,
        # while section 4.7 still shows FC05/06. Use FC06 as the conservative default.
        write_function = 6
        readback_enabled = False
    return {
        "id": f"pcs.{category}.{key}",
        "sheet": "Elecod V2.7.0 PDF",
        "scope": "pcs",
        "category": category,
        "address": address,
        "address_hex": f"0x{address:04X}",
        "key": key,
        "name_en": item or None,
        "name_cn": None,
        "access": access,
        "data_type": data_type,
        "register_width": register_count,
        "element_count": 1,
        "register_count": register_count,
        "scale": scale,
        "offset": None,
        "unit": UNIT_OVERRIDES.get(address, unit_from_value(value)),
        "range_text": value or None,
        "enum": ENUMS.get(address, {}),
        "read_function": read_function,
        "write_function": write_function,
        "write_functions": ([write_function] if write_function else []),
        "readback_enabled": readback_enabled,
        "word_order": "big",
        "poll_class": poll_class(address, reserved),
        "poll_enabled": poll_class(address, reserved) != "disabled",
        "reserved": reserved,
        "source": "Elecod Monet-AC Modbus RTU_TCP protocol V2.7.0",
        "format": fmt or None,
        "notes": None,
    }


def collect_scalar_rows(pdf: pdfplumber.PDF) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    # Pages 12..16 identity + telemetry.
    for page_index in range(11, 16):
        for table in pdf.pages[page_index].extract_tables():
            for row in table:
                if not row or not clean(row[0]).split("\n")[0].isdigit():
                    continue
                ids = [int(x) for x in re.findall(r"\d{4}", clean(row[0]))]
                if not ids:
                    continue
                address = ids[0]
                if not (1000 <= address <= 1108):
                    continue
                byte_count = int(clean(row[1]) or 2)
                if len(row) == 5:
                    item, value, dtype_text, fmt = clean(row[2]), "", clean(row[3]), clean(row[4])
                else:
                    item, value, dtype_text, fmt = clean(row[2]), clean(row[3]), clean(row[4]), clean(row[5])
                points.append(row_to_point(address, byte_count, item, value, dtype_text, fmt, access="R"))

    # Pages 23..41 parameter tables. Merge page-break continuation rows.
    previous: dict[str, Any] | None = None
    for page_index in range(22, 41):
        for table in pdf.pages[page_index].extract_tables():
            for row in table:
                if not row or len(row) < 5:
                    continue
                id_text = clean(row[0])
                byte_text = clean(row[1]) if len(row) > 1 else ""
                item = clean(row[2]) if len(row) > 2 else ""
                value = clean(row[3]) if len(row) > 3 else ""
                dtype_text = clean(row[4]) if len(row) > 4 else ""
                fmt = clean(row[5]) if len(row) > 5 else ""
                ids = [int(x) for x in re.findall(r"\d{4}", id_text)]

                if not ids:
                    if previous is not None and (item or value):
                        if item:
                            previous["name_en"] = clean(f"{previous.get('name_en','')} {item}")
                        if value:
                            previous["range_text"] = clean(f"{previous.get('range_text','')} {value}")
                    continue

                address = ids[0]
                # Continuation register of a 4-byte point split over a page (3095/3096).
                if previous is not None and previous.get("register_count") == 2 and address == int(previous["address"]) + 1 and not byte_text and not dtype_text:
                    if item:
                        previous["name_en"] = clean(f"{previous.get('name_en','')} {item}")
                    if value:
                        previous["range_text"] = clean(f"{previous.get('range_text','')} {value}")
                    continue

                if not ((3050 <= address <= 3360) or (1500 <= address <= 1505) or (5050 <= address <= 5051)):
                    continue
                try:
                    byte_count = int(byte_text) if byte_text else 2
                except ValueError:
                    byte_count = 2
                point = row_to_point(address, byte_count, item, value, dtype_text, fmt, access="RW")
                points.append(point)
                previous = point

    # Replace known page-break truncations with the exact text visible in the PDF.
    by_address = {int(point["address"]): point for point in points}
    for address, (name, value) in SPECIAL_CONTINUATIONS.items():
        if address in by_address:
            by_address[address]["name_en"] = name
            by_address[address]["key"] = CRITICAL_KEYS.get(address, slug(name))
            by_address[address]["id"] = f"pcs.{by_address[address]['category']}.{by_address[address]['key']}"
            if value:
                by_address[address]["range_text"] = value
    return points


def build(pdf_path: Path) -> dict[str, Any]:
    with pdfplumber.open(pdf_path) as pdf:
        points = collect_scalar_rows(pdf)
        bitfields = parse_bit_tables(pdf)

    by_address = {int(point["address"]): point for point in points}
    for address in range(2050, 2058):
        fields = sorted(bitfields.get(address, []), key=lambda item: int(item["bit"]))
        if address not in by_address:
            key = CRITICAL_KEYS[address]
            category = "status" if address == 2057 else "alarm"
            point = {
                "id": f"pcs.{category}.{key}", "sheet": "Elecod V2.7.0 PDF", "scope": "pcs",
                "category": category, "address": address, "address_hex": f"0x{address:04X}", "key": key,
                "name_en": "PCS status word" if address == 2057 else f"Alarm message {address - 2049}",
                "name_cn": None, "access": "R", "data_type": "U16", "register_width": 1,
                "element_count": 1, "register_count": 1, "scale": None, "offset": None, "unit": None,
                "range_text": None, "enum": {}, "read_function": 3, "write_function": None,
                "write_functions": [], "readback_enabled": True, "word_order": "big",
                "poll_class": "fast", "poll_enabled": True, "reserved": False,
                "source": "Elecod Monet-AC Modbus RTU_TCP protocol V2.7.0", "format": "HEX", "notes": None,
            }
            points.append(point)
            by_address[address] = point
        by_address[address]["bitfields"] = fields

    # Add semantic aliases to the status bits used by the pair controller.
    status = by_address[2057]
    status["bitfield_aliases"] = {
        "dc_precharge_connected": 0,
        "ac_soft_start_connected": 1,
        "dc_relay_connected": 2,
        "ac_relay_connected": 3,
        "off_grid": 4,
        "charging": 5,
        "running": 6,
        "fault": 7,
        "standby": 10,
        "shutdown": 11,
        "epo": 12,
        "parameter_initialization_complete": 15,
    }

    # Critical scale fixes and units from explicit vendor definitions.
    telemetry_units_scales = {
        1050: (0.1, "V"), 1051: (0.1, "V"), 1052: (0.1, "V"),
        1053: (0.1, "A"), 1054: (0.1, "A"), 1055: (0.1, "A"),
        1056: (0.01, "Hz"), 1057: (0.01, "Hz"), 1058: (0.01, "Hz"),
        1059: (0.01, None), 1060: (0.1, "kW"), 1061: (0.1, "kvar"),
        1062: (0.1, "kVA"), 1063: (0.1, "V"), 1064: (0.1, "A"),
        1065: (0.1, "kW"), 1066: (0.1, "V"), 1067: (0.1, "V"), 1068: (0.1, "V"),
        1069: (0.1, "A"), 1070: (0.1, "V"), 1071: (1.0, "kΩ"), 1072: (1.0, "kΩ"),
        1073: (0.01, "A"), 1074: (1.0, "℃"), 1075: (1.0, "℃"), 1076: (1.0, "℃"),
        1077: (0.1, "%"), 1078: (0.01, None), 1079: (0.01, None), 1080: (0.01, None),
        1081: (0.1, "kW"), 1082: (0.1, "kW"), 1083: (0.1, "kW"),
        1084: (0.1, "kvar"), 1085: (0.1, "kvar"), 1086: (0.1, "kvar"),
        1087: (0.1, "kVA"), 1088: (0.1, "kVA"), 1089: (0.1, "kVA"),
        1090: (0.1, "V"), 1091: (0.1, "V"), 1092: (0.1, "V"),
        1093: (0.1, "A"), 1094: (0.1, "A"), 1095: (0.1, "A"),
        1105: (0.1, "kWh"), 1107: (0.1, "kWh"),
    }
    for address, (scale, unit) in telemetry_units_scales.items():
        if address in by_address:
            by_address[address]["scale"] = scale
            if unit:
                by_address[address]["unit"] = unit

    for address, scale in SCALE_OVERRIDES.items():
        if address in by_address:
            by_address[address]["scale"] = scale

    # Preserve source order by Modbus address, but identity/time/control address
    # ranges are intentionally non-contiguous.
    points.sort(key=lambda point: int(point["address"]))
    active = [point for point in points if not point.get("reserved")]
    counts: dict[str, int] = {}
    for point in active:
        group = f"{point['scope']}.{point['category']}"
        counts[group] = counts.get(group, 0) + 1

    metadata = {
        "source_file": pdf_path.name,
        "vendor": "Elecod",
        "product": "Monet-AC Series Energy Storage Converter",
        "protocol_version": "V2.7.0",
        "protocols": ["modbus_tcp", "modbus_rtu"],
        "supported_modbus_functions": [3, 4, 6, 16],
        "documented_remote_control_functions": [5, 6],
        "default_tcp_port": 502,
        "rtu_baudrate": 9600,
        "minimum_frame_interval_ms": 100,
        "default_modbus_node": 1,
        "ip65_special_configuration_unit_id": 160,
        "word_order_32bit": "Hi-Lo / MSW first per vendor tables",
        "commissioning_gaps": [
            "Confirm positive active-power command means discharge and negative means charge with low-power test",
            "Confirm FC06 is accepted for registers 5050/5051 on V2.7.0 (revision history conflicts with section 4.7 FC05 example)",
            "Confirm on-grid/off-grid transition sequence and external STS/contactor ownership",
            "Confirm actual four-PCS TCP topology (per-device IP/port/Unit-ID)",
        ],
        "point_count": len(points),
        "active_point_count": len(active),
    }
    return {"metadata": metadata, "counts": counts, "points": points, "reserved_ranges": []}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    payload = build(args.pdf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {args.output}: {len(payload['points'])} points, {payload['metadata']['active_point_count']} active")


if __name__ == "__main__":
    main()
