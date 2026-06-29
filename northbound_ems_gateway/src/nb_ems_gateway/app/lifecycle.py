from __future__ import annotations

import logging

LOGGER = logging.getLogger(__name__)


def install_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
