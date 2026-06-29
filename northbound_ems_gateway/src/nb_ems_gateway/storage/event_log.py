from __future__ import annotations

import logging

LOGGER = logging.getLogger("nb_ems_gateway.events")


def log_event(event: str, **fields) -> None:
    LOGGER.info("%s %s", event, fields)
