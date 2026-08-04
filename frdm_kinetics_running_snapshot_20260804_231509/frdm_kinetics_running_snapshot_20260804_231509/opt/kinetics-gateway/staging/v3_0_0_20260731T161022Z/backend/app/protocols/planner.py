from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReadBlock:
    function_code: int
    start: int
    count: int
    points: tuple[dict[str, Any], ...]


def build_read_blocks(
    points: list[dict[str, Any]],
    *,
    max_registers: int = 120,
    max_gap: int = 2,
) -> list[ReadBlock]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for point in points:
        if point.get("reserved") or point.get("poll_class") == "disabled":
            continue
        function = int(point.get("read_function") or point.get("function_code") or 3)
        grouped.setdefault(function, []).append(point)

    blocks: list[ReadBlock] = []
    for function, entries in grouped.items():
        entries.sort(key=lambda item: int(item["address"]))
        current: list[dict[str, Any]] = []
        start = 0
        end = 0
        for point in entries:
            point_start = int(point["address"])
            point_count = int(point.get("register_count") or 1)
            point_end = point_start + point_count
            if point_count > max_registers:
                if current:
                    blocks.append(ReadBlock(function, start, end - start, tuple(current)))
                    current = []
                # Large arrays are represented as one logical point but split by the driver.
                blocks.append(ReadBlock(function, point_start, point_count, (point,)))
                continue
            if not current:
                current = [point]
                start, end = point_start, point_end
                continue
            proposed_end = max(end, point_end)
            if point_start - end <= max_gap and proposed_end - start <= max_registers:
                current.append(point)
                end = proposed_end
            else:
                blocks.append(ReadBlock(function, start, end - start, tuple(current)))
                current = [point]
                start, end = point_start, point_end
        if current:
            blocks.append(ReadBlock(function, start, end - start, tuple(current)))
    return blocks
