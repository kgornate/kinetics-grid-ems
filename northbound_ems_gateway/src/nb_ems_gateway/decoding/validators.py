from __future__ import annotations

import math


def is_plausible_float(value: float) -> bool:
    if not isinstance(value, float | int):
        return False
    if math.isnan(float(value)) or math.isinf(float(value)):
        return False
    return abs(float(value)) < 1e12


def apply_factor(value: float, factor: float | int | None) -> float:
    if factor is None:
        return float(value)
    return float(value) * float(factor)
