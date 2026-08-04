from __future__ import annotations

import math
import re
import struct
from typing import Any


_TYPE_WIDTH = {
    "U16": 1,
    "S16": 1,
    "U32": 2,
    "S32": 2,
    "U64": 4,
    "S64": 4,
    "FLOAT32": 2,
    "F32": 2,
}


def width_for_type(data_type: str) -> int:
    return _TYPE_WIDTH.get(str(data_type or "U16").upper(), 1)


def _words_to_bytes(words: list[int], word_order: str = "big") -> bytes:
    ordered = list(words)
    if word_order.lower() in {"little", "lsw_first", "cdab"} and len(ordered) > 1:
        ordered.reverse()
    return b"".join(struct.pack(">H", word & 0xFFFF) for word in ordered)


def decode_scalar(words: list[int], data_type: str, *, word_order: str = "big") -> int | float:
    dtype = str(data_type or "U16").upper()
    width = width_for_type(dtype)
    if len(words) < width:
        raise ValueError(f"Need {width} registers for {dtype}, got {len(words)}")
    payload = _words_to_bytes(words[:width], word_order)
    if dtype == "U16":
        return struct.unpack(">H", payload)[0]
    if dtype == "S16":
        return struct.unpack(">h", payload)[0]
    if dtype == "U32":
        return struct.unpack(">I", payload)[0]
    if dtype == "S32":
        return struct.unpack(">i", payload)[0]
    if dtype == "U64":
        return struct.unpack(">Q", payload)[0]
    if dtype == "S64":
        return struct.unpack(">q", payload)[0]
    if dtype in {"FLOAT32", "F32"}:
        return struct.unpack(">f", payload)[0]
    return struct.unpack(">H", payload[:2])[0]


def decode_point(point: dict[str, Any], words: list[int], *, word_order: str = "big") -> dict[str, Any]:
    dtype = str(point.get("data_type") or "U16").upper()
    width = int(point.get("register_width") or width_for_type(dtype))
    count = int(point.get("element_count") or 1)
    scale = point.get("scale")
    values: list[int | float] = []
    raw_values: list[int | float] = []
    for index in range(count):
        start = index * width
        raw = decode_scalar(words[start : start + width], dtype, word_order=word_order)
        raw_values.append(raw)
        value: int | float = raw
        if scale is not None:
            value = raw * float(scale)
            if isinstance(value, float) and not math.isfinite(value):
                value = raw
        values.append(value)
    value_out: Any = values[0] if count == 1 else values
    raw_out: Any = raw_values[0] if count == 1 else raw_values
    bitfields: dict[str, int] = {}
    if count == 1 and point.get("bitfields"):
        integer = int(raw_values[0])
        for bit in point["bitfields"]:
            bitfields[str(bit["key"])] = (integer >> int(bit["bit"])) & 1
    return {
        "value": value_out,
        "raw": raw_out,
        "unit": point.get("unit"),
        "quality": "good",
        "bitfields": bitfields,
    }


def encode_scalar(value: int | float, data_type: str, *, scale: float | None = None, word_order: str = "big") -> list[int]:
    dtype = str(data_type or "U16").upper()
    raw: int | float = value
    if scale not in (None, 0):
        raw = float(value) / float(scale)
    if dtype == "U16":
        payload = struct.pack(">H", int(round(raw)) & 0xFFFF)
    elif dtype == "S16":
        payload = struct.pack(">h", int(round(raw)))
    elif dtype == "U32":
        payload = struct.pack(">I", int(round(raw)) & 0xFFFFFFFF)
    elif dtype == "S32":
        payload = struct.pack(">i", int(round(raw)))
    elif dtype == "U64":
        payload = struct.pack(">Q", int(round(raw)) & 0xFFFFFFFFFFFFFFFF)
    elif dtype == "S64":
        payload = struct.pack(">q", int(round(raw)))
    elif dtype in {"FLOAT32", "F32"}:
        payload = struct.pack(">f", float(raw))
    else:
        payload = struct.pack(">H", int(round(raw)) & 0xFFFF)
    words = [struct.unpack(">H", payload[i : i + 2])[0] for i in range(0, len(payload), 2)]
    if word_order.lower() in {"little", "lsw_first", "cdab"} and len(words) > 1:
        words.reverse()
    return words


def parse_range(range_text: str | None) -> tuple[float | None, float | None]:
    if not range_text:
        return None, None
    nums = re.findall(r"[-+]?\d+(?:\.\d+)?", range_text)
    if len(nums) < 2:
        return None, None
    return float(nums[0]), float(nums[1])


def validate_value(point: dict[str, Any], value: int | float) -> None:
    low, high = parse_range(point.get("range_text"))
    if low is not None and float(value) < low:
        raise ValueError(f"Value {value} is below minimum {low} for {point.get('key')}")
    if high is not None and float(value) > high:
        raise ValueError(f"Value {value} is above maximum {high} for {point.get('key')}")
