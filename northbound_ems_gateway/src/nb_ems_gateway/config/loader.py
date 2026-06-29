from __future__ import annotations

import json
from pathlib import Path

from .models import AppConfig


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    data = json.loads(config_path.read_text(encoding="utf-8"))
    config = AppConfig.model_validate(data)
    config.assert_read_only()
    return config
