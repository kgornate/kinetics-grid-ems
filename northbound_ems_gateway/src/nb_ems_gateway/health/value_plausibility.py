from __future__ import annotations


def is_soc_plausible(value: float | None) -> bool:
    return value is not None and 0 <= value <= 100


def is_frequency_plausible(value: float | None) -> bool:
    return value is not None and 40 <= value <= 70


def is_voltage_plausible(value: float | None) -> bool:
    return value is not None and -2000 <= value <= 2000
