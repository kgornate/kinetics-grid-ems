"""Offline Phase 4: frozen four-pair S2 mapping, bounded messages, durable cadence."""
from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import time
from pathlib import Path

import pytest

from app.central_sync.config import CentralSyncConfig
from app.central_sync.contracts import make_message
from app.central_sync.general_asset_producer import CatalogIndex, GeneralAssetProducer
from app.central_sync.outbox import OutboxCapacityError, OutboxStore
from app.central_sync.s2_chunks import MAX_S2_MESSAGE_BYTES, S2RecordTooLarge, json_bytes, split_s2_records
from app.central_sync.s2_policy import S2PolicyError, S2PolicyManifest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "configs" / "kalpa_s2_policy_frozen_v1_0.json"


def cfg_for(tmp):
    cfg = CentralSyncConfig()
    cfg.identity.gateway_id = "kalpa-phase4-test"
    cfg.identity.site_id = "kalpa-sil"
    cfg.general_assets.catalog_dir = str(ROOT / "generated_protocols")
    cfg.general_assets.s2_policy_manifest_path = str(MANIFEST)
    cfg.general_assets.s2_policy_expected_sha256 = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    cfg.general_assets.status_file = str(tmp / "status.json")
    cfg.outbox.path = str(tmp / "s2.sqlite3")
    cfg.outbox.min_free_space_mb = 0
    return cfg


def new_outbox(cfg):
    return OutboxStore(cfg.outbox.path, min_free_space_mb=0)


def query_messages(outbox):
    rows = outbox.conn.execute(
        "SELECT substream,sequence,message_id,payload_json,payload_bytes FROM outbox_messages ORDER BY created_epoch,substream,sequence"
    ).fetchall()
    return [dict(r) for r in rows]


class SnapshotAPI:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    async def telemetry_snapshot(self):
        return self.snapshot

    async def close(self):
        return None


def test_manifest_exhaustive_catalog_alignment_and_validation(tmp_path):
    manifest = S2PolicyManifest(MANIFEST)
    cat = CatalogIndex(ROOT / "generated_protocols")
    assert len(manifest.by_key) == 2471
    counts = {}
    for (vendor, scope, key), policy in manifest.by_key.items():
        cp = cat.get(vendor, scope, key)
        assert cp is not None
        assert cp["id"] == policy.point_id
        counts[policy.substream] = counts.get(policy.substream, 0) + 1
    assert counts["bms_extended"] == 2255
    assert counts["pcs_extended"] == 86
    assert counts.get("utility_meter", 0) == 0
    malformed = json.loads(MANIFEST.read_text())
    malformed["points"][0]["interval_sec"] = 0
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps(malformed))
    with pytest.raises(S2PolicyError):
        S2PolicyManifest(broken)
    with pytest.raises(S2PolicyError, match="checksum mismatch"):
        S2PolicyManifest(MANIFEST, expected_sha256="0" * 64)
    with pytest.raises(S2PolicyError):
        manifest.resolve("lineage", "rack", "new_field", "bms_extended", None)


def small_snapshot():
    ts = "2026-10-15T09:00:00Z"
    return {
        "timestamp": ts,
        "normalized": {"vendors": {"bms": "lineage", "pcs": "elecod"}},
        "bank": {"asset_id": "bms_bank", "asset_type": "bank", "telemetry": {
            "battery_system_state": {"value": 1, "quality": "good"},
            "protocol_version": {"value": 5, "quality": "good"},
        }},
        "racks": [{"asset_id": "bms_rack_1", "rack_id": 1, "asset_type": "rack", "telemetry": {
            "rack_operating_state": {"value": 1, "quality": "good"},
            "cell_voltage_1": {"value": 3.43, "quality": "good"},
        }}],
        "pcs_devices": {"pcs_1": {"asset_id": "pcs_1", "asset_type": "pcs", "telemetry": {
            "armmajorversionnumber": {"value": 1, "quality": "good"},
        }}},
        "environment": {},
    }


def test_checkpoint_change_heartbeat_and_restart(tmp_path):
    cfg = cfg_for(tmp_path)
    outbox = new_outbox(cfg)
    api = SnapshotAPI(small_snapshot())
    try:
        prod = GeneralAssetProducer(config=cfg, outbox=outbox, local_api=api)
        first = asyncio.run(prod.collect_once())
        assert first["record_count"] == 5
        assert first["message_count"] == 3
        assert asyncio.run(prod.collect_once())["emitted"] is False
        # New process does not replay the initial sweep after restart.
        restarted = GeneralAssetProducer(config=cfg, outbox=outbox, local_api=api)
        assert asyncio.run(restarted.collect_once())["emitted"] is False
        api.snapshot["bank"]["telemetry"]["battery_system_state"]["value"] = 2
        delta = asyncio.run(restarted.collect_once())
        assert delta["record_count"] == 1
        body = [json.loads(r["payload_json"]) for r in query_messages(outbox)]
        ems_messages = [x for x in body if x["substream"] == "ems_system"]
        assert ems_messages[-1]["records"][0]["trigger_reason"] == "change"
        assert [x["sequence"] for x in body if x["substream"] == "ems_system"] == [1, 2]
        assert len({x["message_id"] for x in body}) == len(body)
        # Change a persisted timestamp to trigger a heartbeat (no value change).
        outbox.conn.execute("UPDATE s2_recording_checkpoint SET last_emit_epoch=? WHERE runtime_signal_id LIKE '%battery_system_state'", (time.time()-140,))
        outbox.conn.commit()
        again = GeneralAssetProducer(config=cfg, outbox=outbox, local_api=api)
        heartbeat = asyncio.run(again.collect_once())
        assert heartbeat["record_count"] >= 1
        row = [json.loads(r["payload_json"]) for r in query_messages(outbox) if r["substream"] == "ems_system"][-1]
        assert row["records"][0]["trigger_reason"] == "heartbeat"
    finally:
        outbox.close()


def test_atomic_failure_rolls_back_messages_sequences_and_checkpoints(tmp_path):
    cfg = cfg_for(tmp_path)
    outbox = new_outbox(cfg)
    api = SnapshotAPI(small_snapshot())
    try:
        p = GeneralAssetProducer(config=cfg, outbox=outbox, local_api=api)
        original = outbox.enqueue_s2_atomic
        def reject(*args, **kwargs):
            raise OutboxCapacityError("injected capacity failure")
        outbox.enqueue_s2_atomic = reject
        result = asyncio.run(p.collect_once())
        assert result["reason"] == "outbox_capacity"
        assert not query_messages(outbox)
        assert outbox.s2_load_checkpoints(cfg.general_assets.stream) == {}
        assert outbox.current_sequence(cfg.general_assets.stream, "ems_system") == 0
        outbox.enqueue_s2_atomic = original
        retry = asyncio.run(p.collect_once())
        assert retry["record_count"] == 5
        assert outbox.current_sequence(cfg.general_assets.stream, "ems_system") == 1
        # Force a failure after the first INSERT inside a batch transaction.
        with pytest.raises(S2RecordTooLarge):
            outbox.enqueue_s2_atomic(
                config=cfg, stream=cfg.general_assets.stream, substream="pcs_extended", priority="P3",
                chunks=[[{"runtime_signal_id": "ok", "value": 1}],
                        [{"runtime_signal_id": "huge", "value": "Z" * 120000}]],
                checkpoints={"dummy": (time.time(), "fingerprint", "revision")},
                created_at_utc="2026-10-15T09:00:00Z", max_message_bytes=MAX_S2_MESSAGE_BYTES,
            )
        assert outbox.current_sequence(cfg.general_assets.stream, "pcs_extended") == 1
        assert len([r for r in query_messages(outbox) if r["substream"] == "pcs_extended"]) == 1
        assert "dummy" not in outbox.s2_load_checkpoints(cfg.general_assets.stream)
    finally:
        outbox.close()


def four_pair_snapshot():
    catalog = CatalogIndex(ROOT / "generated_protocols")
    manifest = S2PolicyManifest(MANIFEST)
    ts = "2026-10-15T09:00:00Z"
    assets = {
        "bank": {"asset_id": "bms_bank", "asset_type": "bank", "telemetry": {}, "timestamp": ts},
        "env": {"asset_id": "safety_io", "asset_type": "environment", "telemetry": {}, "timestamp": ts},
        "racks": [{"asset_id": f"bms_rack_{i}", "asset_type": "rack", "rack_id": i, "telemetry": {}, "timestamp": ts} for i in range(1, 5)],
        "pcs": [{"asset_id": f"pcs_{i}", "asset_type": "pcs", "telemetry": {}, "timestamp": ts} for i in range(1, 5)],
    }
    for (vendor, scope, key), policy in manifest.by_key.items():
        assert catalog.get(vendor, scope, key) is not None
        if scope == "bank": targets = [assets["bank"]]
        elif scope == "environment": targets = [assets["env"]]
        elif scope == "rack": targets = assets["racks"]
        else: targets = assets["pcs"]
        for target in targets:
            target["telemetry"][key] = {"value": 0, "quality": "good"}
    return {"timestamp": ts, "normalized": {"vendors": {"bms": "lineage", "pcs": "elecod"}},
            "bank": assets["bank"], "racks": assets["racks"],
            "pcs_devices": {x["asset_id"]: x for x in assets["pcs"]},
            "environment": {"safety_io": assets["env"]}}


def test_four_pair_full_initial_sweep_bounded_exact_outbox_and_restart(tmp_path):
    cfg = cfg_for(tmp_path)
    outbox = new_outbox(cfg)
    try:
        api = SnapshotAPI(four_pair_snapshot())
        prod = GeneralAssetProducer(config=cfg, outbox=outbox, local_api=api)
        result = asyncio.run(prod.collect_once())
        assert result["record_count"] == 9494
        assert result["message_count"] > 9
        messages = query_messages(outbox)
        assert len(messages) == result["message_count"]
        assert all(row["payload_bytes"] <= MAX_S2_MESSAGE_BYTES for row in messages)
        assert sum(json.loads(row["payload_json"])["record_count"] for row in messages) == 9494
        assert len(set(row["message_id"] for row in messages)) == len(messages)
        assert all(len(row["payload_json"].encode("utf-8")) == row["payload_bytes"] for row in messages)
        streams = {row["substream"] for row in messages}
        assert len(streams) == 8
        for sub in streams:
            seqs = [row["sequence"] for row in messages if row["substream"] == sub]
            assert seqs == list(range(1, len(seqs) + 1))
        assert len(outbox.s2_load_checkpoints(cfg.general_assets.stream)) == 9494
        reopened = GeneralAssetProducer(config=cfg, outbox=outbox, local_api=api)
        assert asyncio.run(reopened.collect_once())["emitted"] is False
    finally:
        outbox.close()


def test_single_oversized_signal_rejected_not_silently_truncated():
    with pytest.raises(S2RecordTooLarge):
        split_s2_records([{"runtime_signal_id":"single","value":"🙂" * 60000}])


def test_legacy_s2_unmodified_without_manifest(tmp_path):
    cfg = cfg_for(tmp_path)
    cfg.general_assets.s2_policy_manifest_path = None
    outbox = new_outbox(cfg)
    try:
        p = GeneralAssetProducer(config=cfg,outbox=outbox,local_api=SnapshotAPI(small_snapshot()))
        result = asyncio.run(p.collect_once())
        assert result["record_count"] == 5
        assert outbox.s2_load_checkpoints(cfg.general_assets.stream) == {}
    finally:
        outbox.close()
