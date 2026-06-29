from __future__ import annotations

import logging
from dataclasses import dataclass

from nb_ems_gateway.config.models import DecodingConfig, PollingConfig
from nb_ems_gateway.decoding.float32_decoder import Float32Decoder
from nb_ems_gateway.decoding.quality import PointQuality
from nb_ems_gateway.decoding.validators import apply_factor, is_plausible_float
from nb_ems_gateway.protocol.modbus_client import RegisterReader
from nb_ems_gateway.protocol.read_plan import ReadPlan
from .poll_result import DecodedPointValue, PollResult

LOGGER = logging.getLogger(__name__)


@dataclass
class PollingService:
    reader: RegisterReader
    plans: dict[str, ReadPlan]
    decoding_config: DecodingConfig
    polling_config: PollingConfig

    def __post_init__(self) -> None:
        self.decoder = Float32Decoder(self.decoding_config.byte_order)

    def poll_once(self, poll_group: str) -> PollResult:
        plan = self.plans[poll_group]
        decoded: list[DecodedPointValue] = []
        errors: list[str] = []
        for chunk in plan.chunks:
            try:
                registers = self.reader.read_registers(chunk.start_address, chunk.register_count)
            except Exception as exc:
                message = f"Chunk read failed group={poll_group} start={chunk.start_address} count={chunk.register_count}: {exc}"
                errors.append(message)
                LOGGER.warning(message)
                for point in chunk.points:
                    decoded.append(
                        _point_value(
                            point,
                            value=None,
                            quality=PointQuality.COMMUNICATION_ERROR,
                            error=str(exc),
                        )
                    )
                continue
            base = chunk.start_address
            for point in chunk.points:
                offset = point.address - base
                raw = registers[offset:offset + point.register_qty]
                try:
                    if len(raw) != 2:
                        raise ValueError(f"Expected 2 registers, got {len(raw)}")
                    value = self.decoder.decode((raw[0], raw[1]))
                    if self.decoding_config.apply_factor:
                        value = apply_factor(value, point.factor)
                    if not is_plausible_float(value):
                        decoded.append(
                            _point_value(
                                point,
                                value=None,
                                quality=PointQuality.PLAUSIBILITY_ERROR,
                                raw_registers=_raw_tuple(raw),
                                error="Decoded float failed plausibility check",
                            )
                        )
                    else:
                        decoded.append(
                            _point_value(
                                point,
                                value=float(value),
                                quality=PointQuality.GOOD,
                                raw_registers=_raw_tuple(raw),
                            )
                        )
                except Exception as exc:
                    decoded.append(
                        _point_value(
                            point,
                            value=None,
                            quality=PointQuality.DECODE_ERROR,
                            raw_registers=_raw_tuple(raw),
                            error=str(exc),
                        )
                    )
        return PollResult(poll_group=poll_group, values=tuple(decoded), errors=tuple(errors))


def _raw_tuple(raw) -> tuple[int, int] | None:
    return (int(raw[0]), int(raw[1])) if len(raw) >= 2 else None


def _point_value(point, *, value, quality: PointQuality, raw_registers=None, error: str | None = None) -> DecodedPointValue:
    return DecodedPointValue.now(
        point_id=point.point_id,
        asset_id=point.asset_id or "unknown",
        normalized_name=point.normalized_name or point.point_name,
        address=point.address,
        point_name=point.point_name,
        entity_name=point.entity_name,
        value=value,
        unit=point.unit,
        quality=quality,
        raw_registers=raw_registers,
        error=error,
        display_name=point.display_name,
        category=point.category,
        dashboard_group=point.dashboard_group,
        is_key_signal=point.is_key_signal,
        enum_map=point.enum_map,
    )
