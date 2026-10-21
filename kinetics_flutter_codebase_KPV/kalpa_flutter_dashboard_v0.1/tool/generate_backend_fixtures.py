"""Generate fixture contracts from an isolated Kalpa backend checkout, never a live gateway.
Usage: python generate_backend_fixtures.py /path/to/backend
"""
import json
from pathlib import Path
import sys
import tempfile

backend = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(backend))
from app.core.config import GatewayConfig
from app.storage.sqlite_store import SQLiteStore
from app.services.gateway_service import GatewayService

payload = json.loads((backend / "configs/elecod_lineage_4pair_sil.json").read_text())
payload["mode"] = "mock"
payload["bms"]["write_enabled"] = False
payload["pcs"]["write_enabled"] = False
payload["control_sequence"]["enabled"] = False
payload["control_sequence"]["allow_full_automatic_sequence"] = False
payload["meter"] = {"enabled": True, "mode": "mock"}
with tempfile.TemporaryDirectory() as temporary:
    payload["storage"].update(preferred_mount_point=temporary + "/absent", fallback_root=temporary + "/db", require_preferred_mount=False)
    config = GatewayConfig.model_validate(payload)
    service = GatewayService(config, SQLiteStore(config.storage))
    service.poll_meter()
    target = Path(__file__).resolve().parents[1] / "test/fixtures"
    target.mkdir(parents=True, exist_ok=True)
    fixtures = {
        "compact": service.compact_snapshot(),
        "normalized": service.normalized_snapshot(),
        "meter": service.meters(),
        "control_capabilities": service.control_sequence.capabilities(),
        "control_all_compact": service.control_sequence.all_pair_status_compact(),
        "control_pair": service.control_sequence.status("pair_1", fresh=False),
    }
    for name, data in fixtures.items():
        (target / (name + ".json")).write_text(json.dumps(data))
print("Generated isolated mock backend fixtures; all write gates disabled.")
