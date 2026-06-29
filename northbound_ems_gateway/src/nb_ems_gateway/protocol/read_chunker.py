from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from nb_ems_gateway.dictionary.register_point import RegisterPoint


@dataclass(frozen=True)
class ReadChunk:
    start_address: int
    register_count: int
    points: tuple[RegisterPoint, ...]

    @property
    def end_address_exclusive(self) -> int:
        return self.start_address + self.register_count


def build_read_chunks(points: Iterable[RegisterPoint], max_registers_per_read: int = 120) -> list[ReadChunk]:
    ordered = sorted(points, key=lambda p: p.address)
    chunks: list[ReadChunk] = []
    current_points: list[RegisterPoint] = []
    start: int | None = None
    end: int | None = None

    for point in ordered:
        p_start = point.address
        p_end = point.address + point.register_qty
        if start is None:
            start, end = p_start, p_end
            current_points = [point]
            continue
        proposed_start = start
        proposed_end = max(end or p_end, p_end)
        proposed_count = proposed_end - proposed_start
        if proposed_count <= max_registers_per_read:
            current_points.append(point)
            end = proposed_end
        else:
            chunks.append(ReadChunk(start_address=start, register_count=(end or start) - start, points=tuple(current_points)))
            start, end = p_start, p_end
            current_points = [point]

    if start is not None and end is not None and current_points:
        chunks.append(ReadChunk(start_address=start, register_count=end - start, points=tuple(current_points)))
    return chunks
