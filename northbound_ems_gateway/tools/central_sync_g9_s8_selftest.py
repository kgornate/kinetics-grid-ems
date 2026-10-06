#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
from pathlib import Path

from nb_ems_gateway.central_sync.config import load_central_sync_config
from nb_ems_gateway.central_sync.configuration_audit_producer import ConfigurationAuditProducer
from nb_ems_gateway.central_sync.outbox import OutboxStore


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def rows(db: Path, stream: str) -> list[dict]:
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        values = conn.execute(
            "SELECT payload_json FROM outbox_messages WHERE stream=? ORDER BY sequence", (stream,)
        ).fetchall()
    return [json.loads(r["payload_json"]) for r in values]


async def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db = root / "outbox.db"
        cfg_path = root / "central_sync.json"
        settings_path = root / "control_settings.json"
        status_path = root / "operator_status.json"
        manifest_path = root / "manifest.json"
        state_path = root / "s8_state.json"
        producer_status_path = root / "s8_status.json"

        cfg = {
            "enabled": True,
            "identity": {
                "site_id": "site-test",
                "gateway_id": "gw-test",
                "schema_version": "1.0",
                "software_version": "central-sync-g9-s8-config-audit",
            },
            "backend": {
                "base_url": "https://example.invalid",
                "ingest_path": "/api/v1/ingest/batch",
                "verify_tls": True,
            },
            "outbox": {"path": str(db), "max_db_size_mb": 128, "min_free_space_mb": 0, "fail_if_mount_missing": False},
            "fast_bess": {"sample_interval_sec": 1.0},
            "general_assets": {"policy_manifest_path": "data/central_sync/canonical_signal_policy_frozen_v1_1.json"},
            "edge_ai": {"enabled": False, "model_manifest_path": str(manifest_path)},
            "configuration_audit": {
                "enabled": True,
                "poll_interval_sec": 1.0,
                "controller_settings_path": str(settings_path),
                "controller_status_path": str(status_path),
                "model_manifest_path": str(manifest_path),
                "state_file": str(state_path),
                "status_file": str(producer_status_path),
            },
            "overflow_archive": {"enabled": False},
            "backlog_replay": {"enabled": False},
        }
        write_json(cfg_path, cfg)
        write_json(settings_path, {
            "schema_version": 2,
            "revision": 6,
            "updated_at_utc": "2026-09-28T00:00:00Z",
            "updated_by": "field_admin",
            "values": {
                "derate_soc_limit": 90.0,
                "derate_power_kw": 20.0,
                "high_limit": 98.0,
                "recovery_limit": 75.0,
                "low_cutoff_limit": 10.0,
                "low_recovery_limit": 10.0,
            },
        })
        write_json(status_path, {"timestamp_utc": "2026-09-28T00:00:00Z", "thresholds": {"low_cutoff_enabled": False}})
        write_json(manifest_path, {
            "version": "v0_3",
            "threshold": 0.5691796048965233,
            "threshold_direction": "anomaly_score_ml >= threshold means anomaly",
            "feature_count": 33,
            "features": [f"f{i}" for i in range(33)],
        })

        config = load_central_sync_config(cfg_path)
        outbox = OutboxStore(str(db), max_db_size_mb=128, min_free_space_mb=0, fail_if_mount_missing=False)
        try:
            # Preserve an existing unrelated stream sequence and prove S8 isolation.
            s1_before = outbox.next_sequence("fast_bess_telemetry", "critical_pcs_bms")
            producer = ConfigurationAuditProducer(config=config, outbox=outbox, central_sync_config_path=str(cfg_path))

            result = await producer.collect_once()
            assert result["baseline_created"] is True
            assert rows(db, "configuration_audit") == []
            print("PASS: first S8 observation baselines current config without fabricated audit history")

            # Revisioned controller change -> one deterministic S8 audit event.
            settings = json.loads(settings_path.read_text())
            settings["revision"] = 7
            settings["updated_at_utc"] = "2026-10-06T10:00:00Z"
            settings["updated_by"] = "kunal"
            settings["values"]["high_limit"] = 97.0
            write_json(settings_path, settings)
            result = await producer.collect_once()
            assert result["emitted_changes"] == 1
            msg = rows(db, "configuration_audit")[-1]
            rec = msg["records"][0]
            assert rec["setting_path"] == "controller.high_limit"
            assert rec["old_value"] == 98.0 and rec["new_value"] == 97.0
            assert rec["revision"] == 7
            assert rec["actor"] == "kunal" and rec["actor_role"] == "internal_admin"
            assert rec["change_source"] == "local_api"
            assert msg["message_id"] == rec["audit_id"]
            print("PASS: revisioned controller setting change emits contract-compliant stable S8 event")

            # Config change -> one S8 event; secret/token fields are not in snapshot.
            raw = json.loads(cfg_path.read_text())
            raw["backend"]["verify_tls"] = False
            write_json(cfg_path, raw)
            result = await producer.collect_once()
            assert result["emitted_changes"] == 1
            rec = rows(db, "configuration_audit")[-1]["records"][0]
            assert rec["setting_path"] == "central_sync.tls_verify"
            assert rec["old_value"] is True and rec["new_value"] is False
            assert rec["change_source"] == "config_file"
            print("PASS: Central Sync non-secret configuration change emits S8 audit")

            # Model change -> one model_update event.
            manifest = json.loads(manifest_path.read_text())
            manifest["threshold"] = 0.6
            write_json(manifest_path, manifest)
            result = await producer.collect_once()
            assert result["emitted_changes"] == 1
            rec = rows(db, "configuration_audit")[-1]["records"][0]
            assert rec["setting_path"] == "edge_ai.threshold"
            assert rec["change_source"] == "model_update"
            print("PASS: Edge-AI manifest change emits S8 model_update audit")

            # Missing optional runtime source does not emit value->null noise.
            status_path.unlink()
            result = await producer.collect_once()
            assert result["emitted_changes"] == 0
            print("PASS: temporary optional-source loss does not fabricate configuration changes")

            # Recreate with changed low-cutoff flag. First reappearance is compared
            # to preserved baseline because missing sources never delete old state.
            write_json(status_path, {"timestamp_utc": "2026-10-06T10:05:00Z", "thresholds": {"low_cutoff_enabled": True}})
            result = await producer.collect_once()
            assert result["emitted_changes"] == 1
            rec = rows(db, "configuration_audit")[-1]["records"][0]
            assert rec["setting_path"] == "controller.low_cutoff_enabled"
            assert rec["old_value"] is False and rec["new_value"] is True
            print("PASS: runtime low-cutoff enable transition is audited without source-outage noise")

            # No further change -> no duplicate event.
            count_before = len(rows(db, "configuration_audit"))
            result = await producer.collect_once()
            assert result["emitted_changes"] == 0
            assert len(rows(db, "configuration_audit")) == count_before
            print("PASS: unchanged configuration does not generate duplicate S8 traffic")

            assert outbox.current_sequence("fast_bess_telemetry", "critical_pcs_bms") == s1_before
            assert config.backlog_replay.enabled is False
            print("PASS: S8 leaves existing stream sequences untouched and backlog replay disabled")
        finally:
            outbox.close()

    print("G9_S8_SELFTEST=PASS")


if __name__ == "__main__":
    asyncio.run(main())
