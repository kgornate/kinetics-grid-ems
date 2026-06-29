from __future__ import annotations

from dataclasses import dataclass

from nb_ems_gateway.dictionary.register_map import RegisterMap
from .read_chunker import ReadChunk, build_read_chunks


@dataclass(frozen=True)
class ReadPlan:
    poll_group: str
    chunks: tuple[ReadChunk, ...]


def create_read_plans(register_map: RegisterMap, max_registers_per_read: int = 120) -> dict[str, ReadPlan]:
    plans: dict[str, ReadPlan] = {}
    for group in sorted({p.poll_group for p in register_map.points}):
        group_points = register_map.by_poll_group(group)
        chunks = build_read_chunks(group_points, max_registers_per_read=max_registers_per_read)
        plans[group] = ReadPlan(poll_group=group, chunks=tuple(chunks))
    return plans
