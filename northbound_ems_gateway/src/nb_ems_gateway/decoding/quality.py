from __future__ import annotations

from enum import StrEnum


class PointQuality(StrEnum):
    GOOD = "good"
    STALE = "stale"
    COMMUNICATION_ERROR = "communication_error"
    DECODE_ERROR = "decode_error"
    PLAUSIBILITY_ERROR = "plausibility_error"
    NOT_POLLED = "not_polled"
