import json
from pathlib import Path
from .models import AppConfig

def load_config(path: str | None) -> AppConfig:
    if not path:
        return AppConfig()
    return AppConfig.model_validate(json.loads(Path(path).read_text()))
