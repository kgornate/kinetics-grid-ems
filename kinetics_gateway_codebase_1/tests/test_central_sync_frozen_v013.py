from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from app.central_sync.alarm_event_producer import AlarmEventProducer
from app.central_sync.charge_discharge_producer import ChargeDischargeProducer
from app.central_sync.command_downlink import CommandDownlinkProcessor
from app.central_sync.config import CentralSyncConfig
from app.central_sync.configuration_audit_producer import ConfigurationAuditProducer
from app.central_sync.contracts import LogicalMessage, make_message
from app.central_sync.fast_bess_producer import FastBESSProducer
from app.central_sync.gateway_health_producer import GatewayHealthProducer
from app.central_sync.general_asset_producer import CatalogIndex, GeneralAssetProducer, S2_SUBSTREAMS, classify_substream
from app.central_sync.outbox import OutboxStore

ROOT = Path(__file__).resolve().parents[1]

FROZEN_ENVELOPE_FIELDS = {
    "schema_version", "message_id", "gateway_id", "site_id", "organization_id",
    "stream", "substream", "sequence", "created_at_utc", "record_count", "records",
    "compression", "gateway_software_version",
}
FROZEN_S9_FIELDS = {
    "command_id", "correlation_id", "gateway_id", "site_id", "requested_at_utc",
    "received_at_utc", "requested_by", "requested_role", "command_type", "source_id",
    "asset_id", "signal_name", "requested_value", "gateway_validation_ok",
    "validation_reason", "execution_started_at_utc", "execution_finished_at_utc", "write_ok",
    "readback_requested", "readback_value", "verified", "final_status", "failure_reason",
    "gateway_error_code", "duration_ms", "note",
}
FROZEN_S4_FIELDS = {
    "event_id", "correlation_id", "timestamp_utc", "gateway_id", "site_id", "source_id",
    "asset_id", "signal_name", "event_type", "severity", "state", "previous_value",
    "current_value", "message", "controller_state", "decision", "payload", "dedupe_key",
    "occurrence_count", "cleared_at_utc",
}


def run(coro):
    return asyncio.run(coro)


def config_for(tmp_path: Path) -> CentralSyncConfig:
    cfg = CentralSyncConfig()
    cfg.enabled = True
    cfg.identity.gateway_id = "kalpa-test-gateway"
    cfg.identity.site_id = "kalpa-test"
    cfg.identity.organization_id = "ornate-solar"
    cfg.identity.software_version = "kalpa-central-sync-v0.12-test"
    cfg.backend.gzip_enabled = True
    cfg.outbox.path = str(tmp_path / "outbox.db")
    cfg.outbox.required_mount_path = None
    cfg.outbox.fail_if_mount_missing = False
    cfg.outbox.min_free_space_mb = 0
    cfg.general_assets.catalog_dir = str(ROOT / "generated_protocols")
    cfg.fast_bess.status_file = str(tmp_path / "s1.json")
    cfg.general_assets.status_file = str(tmp_path / "s2.json")
    cfg.gateway_health.status_file = str(tmp_path / "s3.json")
    cfg.alarms_events.status_file = str(tmp_path / "s4.json")
    cfg.alarms_events.state_file = str(tmp_path / "s4_state.json")
    cfg.configuration_audit.status_file = str(tmp_path / "s8.json")
    cfg.configuration_audit.state_file = str(tmp_path / "s8_state.json")
    cfg.configuration_audit.gateway_config_path = str(tmp_path / "gateway.json")
    cfg.configuration_audit.central_sync_config_path = str(tmp_path / "central.json")
    cfg.charge_discharge.status_file = str(tmp_path / "s10.json")
    cfg.command_downlink.ledger_path = str(tmp_path / "command_ledger.db")
    cfg.command_downlink.status_file = str(tmp_path / "d1.json")
    return cfg


def payloads(outbox: OutboxStore) -> list[dict]:
    rows = outbox.conn.execute("SELECT payload_json FROM outbox_messages ORDER BY created_epoch, rowid").fetchall()
    return [json.loads(r["payload_json"]) for r in rows]


class FakeApi:
    def __init__(self):
        self.alarm_history_rows = []
        self.posts = []

    async def normalized_snapshot(self):
        return {
            "sequence": 101,
            "timestamp": "2026-10-09T12:00:00Z",
            "pairs": {
                "pair_1": {
                    "enabled": True, "rack_id": 1, "pcs_asset_id": "pcs_1",
                    "battery": {
                        "asset_id": "bms_rack_1", "timestamp": "2026-10-09T12:00:00Z",
                        "state": "Normal", "state_code": 48059, "voltage_v": 700.0,
                        "current_a": -10.0, "soc_percent": 55.0, "soh_percent": 98.0,
                        "max_charge_power_kw": 150.0, "max_discharge_power_kw": 170.0,
                        "max_charge_current_a": 220.0, "max_discharge_current_a": 250.0,
                        "positive_contactor_closed": True, "negative_contactor_closed": True,
                        "positive_insulation_mohm": 10.0, "negative_insulation_mohm": 11.0,
                        "max_cell_voltage_v": 3.48, "min_cell_voltage_v": 3.41,
                        "max_cell_temperature_c": 31.0, "min_cell_temperature_c": 27.0,
                        "charge_allowed": True, "discharge_allowed": True, "blocking_reasons": [],
                    },
                    "pcs": {
                        "asset_id": "pcs_1", "timestamp": "2026-10-09T12:00:00Z",
                        "running": True, "charging": True, "discharging": False, "faulted": False,
                        "standby": False, "shutdown": False, "epo": False, "off_grid": False,
                        "dc_precharge_connected": True, "dc_relay_connected": True, "ac_relay_connected": True,
                        "active_power_kw": -50.0, "reactive_power_kvar": 0.0, "power_factor": 1.0,
                        "dc_voltage_v": 700.0, "dc_current_a": -71.4, "dc_power_kw": -50.0,
                        "dc_bus_voltage_v": 710.0, "grid_frequency_hz": 50.0,
                        "grid_voltage_ab_v": 415.0, "grid_voltage_bc_v": 414.0, "grid_voltage_ca_v": 416.0,
                        "raw_status": 71,
                    },
                }
            },
        }

    async def telemetry_snapshot(self):
        ts = "2026-10-09T12:00:00Z"
        return {
            "timestamp": ts,
            "normalized": {"vendors": {"bms": "lineage", "pcs": "elecod"}},
            "bank": {
                "asset_id": "bms_bank", "asset_type": "bank", "online": True, "timestamp": ts,
                "telemetry": {
                    "protocol_version": {"value": 5, "quality": "good"},
                    "installed_rack_count": {"value": 4, "quality": "good"},
                    "emergency_stop_input": {"value": 0, "quality": "good"},
                },
            },
            "racks": [{
                "asset_id": "bms_rack_1", "asset_type": "rack", "rack_id": 1, "online": True, "timestamp": ts,
                "telemetry": {
                    "cell_001_voltage": {"value": 3.42, "quality": "good", "unit": "V"},
                    "protocol_version": {"value": 5, "quality": "good"},
                },
            }],
            "pcs_devices": {
                "pcs_1": {
                    "asset_id": "pcs_1", "asset_type": "pcs", "online": True, "timestamp": ts,
                    "telemetry": {
                        "armmajorversionnumber": {"value": 2, "quality": "good"},
                    },
                }
            },
            "environment": {},
        }

    async def health(self):
        return {
            "status": "ok", "timestamp": "2026-10-09T12:00:00Z", "mode": "mock",
            "control_sequence": {"enabled": True},
            "network": {"bms_interface": "eth1", "pcs_interface": "eth1", "field_interface": "eth1"},
            "storage": {
                "root": "/tmp", "database": "/tmp/db.sqlite", "free_bytes": 1000000000,
                "filesystem_total_bytes": 2000000000, "database_bytes": 12345,
                "preferred_mount_point": None, "preferred_mount_ready": True,
                "storage_mode": "fallback", "effective_sample_interval_seconds": 5.0,
                "effective_retention_days": 90, "records": {"telemetry": 100, "events": 4},
            },
        }

    async def alarms_history(self, **params):
        return {"history": list(self.alarm_history_rows)}

    async def control_status_compact(self):
        return {
            "timestamp": "2026-10-09T12:00:00Z",
            "pairs": {
                "pair_1": {
                    "pair_id": "pair_1", "stage": "RUNNING", "run_status": "running",
                    "direction": "charge", "requested_power_kw": 50.0, "commanded_power_kw": -50.0,
                    "rack_voltage_v": 700.0, "rack_soc_percent": 55.0, "battery_ready": True,
                    "pcs_running": True, "pcs_actual_power_kw": -49.5, "hard_blocked": False, "errors": [],
                }
            },
            "summary": {"parallel_operation_supported": True, "active_pairs": ["pair_1"], "starting_pairs": [], "startup_policy": "parallel"},
        }

    async def platform_readiness(self):
        return {"ready": True, "commissioning": {"status": "SIL_ONLY"}}

    async def post_json(self, path, payload):
        self.posts.append((path, payload))
        return {"ok": True, "path": path, "payload": payload}


class FakeBackend:
    async def close(self):
        return None



def test_frozen_envelope_required_fields_and_record_count(tmp_path):
    msg = make_message(
        schema_version="1.0", gateway_id="gw", site_id="site", organization_id="org",
        gateway_software_version="v1", stream="gateway_health", substream="gateway",
        sequence=1, priority="P2", records=[{"status": "ok"}], compression="gzip",
    )
    body = msg.model_dump(mode="json")
    assert FROZEN_ENVELOPE_FIELDS <= set(body)
    assert body["record_count"] == len(body["records"]) == 1
    assert body["priority"] == "P2"  # additive Northbound transport hint
    try:
        LogicalMessage(**{**body, "record_count": 2})
    except ValueError:
        pass
    else:
        raise AssertionError("record_count mismatch must fail validation")


def test_s1_emits_northbound_style_bess_record(tmp_path):
    cfg = config_for(tmp_path); outbox = OutboxStore(cfg.outbox.path, min_free_space_mb=0)
    try:
        result = run(FastBESSProducer(config=cfg, outbox=outbox, local_api=FakeApi()).collect_once())
        assert result["emitted"] is True
        p = payloads(outbox)[0]
        assert p["stream"] == "fast_bess_telemetry" and p["substream"] == "bess_fast"
        r = p["records"][0]
        required = {"record_type","sample_source","timestamp_utc","timestamp_epoch_ms","source_id","bess_id","pcs_asset_id","bms_asset_id","profile_name","pcs_values","bms_values","selected_signal_count","quality"}
        assert required <= set(r)
        assert r["record_type"] == "fast_bess_sample"
        assert r["pcs_values"]["active_power_kw"]["value"] == -50.0
        assert r["bms_values"]["soc_percent"]["value"] == 55.0
    finally:
        outbox.close()


def test_s2_frozen_substream_taxonomy_and_classifier():
    assert S2_SUBSTREAMS == (
        "ems_system", "pcs_extended", "bms_extended", "io_module", "liquid_cooling",
        "fire_protection", "dehumidifier", "remote_control", "utility_meter",
    )
    assert classify_substream({"asset_id":"bms_bank","asset_type":"bank"}, "protocol_version", {"category":"system_data","access":"R"}) == "ems_system"
    assert classify_substream({"asset_id":"pcs_1","asset_type":"pcs"}, "armmajorversionnumber", {"category":"identity","access":"R"}) == "pcs_extended"
    assert classify_substream({"asset_id":"bms_rack_1","asset_type":"rack","rack_id":1}, "cell_001_voltage", {"category":"cell_voltage","access":"R"}) == "bms_extended"
    assert classify_substream({"asset_id":"env_1","asset_type":"environment"}, "ambient_temp", {"category":"temp_humidity","access":"R"}) == "io_module"
    assert classify_substream({"asset_id":"bms_bank","asset_type":"bank"}, "chiller_supply_temp", {"category":"chiller","access":"R"}) == "liquid_cooling"
    assert classify_substream({"asset_id":"bms_bank","asset_type":"bank"}, "fire_fault", {"category":"status","access":"R"}) == "fire_protection"
    assert classify_substream({"asset_id":"bms_bank","asset_type":"bank"}, "dehumidifier_enable", {"category":"dehumidifier","access":"R"}) == "dehumidifier"
    assert classify_substream({"asset_id":"pcs_1","asset_type":"pcs"}, "active_power_setting", {"category":"control_parameter","access":"RW"}) == "remote_control"


def test_s2_emits_frozen_point_record_shape(tmp_path):
    cfg = config_for(tmp_path); outbox = OutboxStore(cfg.outbox.path, min_free_space_mb=0)
    try:
        prod = GeneralAssetProducer(config=cfg, outbox=outbox, local_api=FakeApi(), catalog=CatalogIndex(cfg.general_assets.catalog_dir))
        result = run(prod.collect_once())
        assert result["emitted"] is True
        items = payloads(outbox)
        assert {x["substream"] for x in items} <= set(S2_SUBSTREAMS)
        records = [r for x in items for r in x["records"]]
        required = {"record_type","sample_source","persisted_source","observed_at_utc","source_updated_utc","source_id","runtime_asset_id","base_asset_id","substream","runtime_signal_id","point_id","signal","display_name","value","quality","policy","central_record_sec","upload_batch_sec","signal_priority","retention_class","rw","key_signal","trigger_reason"}
        assert records and all(required <= set(r) for r in records)
        assert any(r["substream"] == "ems_system" for r in records)
        assert any(r["substream"] == "pcs_extended" for r in records)
    finally:
        outbox.close()


def test_s3_contains_frozen_gateway_health_fields(tmp_path):
    cfg = config_for(tmp_path); outbox = OutboxStore(cfg.outbox.path, min_free_space_mb=0)
    try:
        prod = GatewayHealthProducer(config=cfg, outbox=outbox, local_api=FakeApi(), central_status_provider=lambda: {"running":True,"counters":{"accepted_count":3,"transport_failure_count":1},"last_upload_utc":"2026-10-09T12:00:00Z","last_ack_utc":"2026-10-09T12:00:01Z","last_error":None})
        result = run(prod.collect_once(force_heartbeat=True))
        assert result["emitted"] is True
        r = payloads(outbox)[0]["records"][0]
        top = {"status","timestamp_utc","gateway_mode","source_count","asset_count","online_asset_count","total_signal_count","bad_signal_count","commands_enabled","control_enabled","storage_can_write","sources","storage","legacy_server_upload","fast_bess_logger","gateway_id","gateway_name","software_version","system_uptime_sec","cpu_percent","memory_used_percent","load_1m","load_5m","load_15m","internet_reachable","interfaces","services","central_sync"}
        assert top <= set(r)
        assert {"running","outbox_pending","outbox_oldest_age_sec","last_upload_utc","last_ack_utc","success_count","failure_count","last_error"} <= set(r["central_sync"])
        assert {"telemetry_snapshots","telemetry_points","gateway_events","fast_bess_samples"} <= set(r["storage"]["tables"])
    finally:
        outbox.close()


def test_s4_first_start_does_not_dump_old_history_then_emits_exact_event_shape(tmp_path):
    cfg = config_for(tmp_path); outbox = OutboxStore(cfg.outbox.path, min_free_space_mb=0); api = FakeApi()
    try:
        api.alarm_history_rows = [{"timestamp":"2026-10-09T10:00:00Z","alarm_key":"old","asset_id":"bms_rack_1","action":"raised","severity":"warning","payload":{}}]
        prod = AlarmEventProducer(config=cfg, outbox=outbox, local_api=api)
        first = run(prod.collect_once())
        assert first["emitted"] is False and first["reason"] == "baseline_established"
        assert payloads(outbox) == []
        api.alarm_history_rows.append({"timestamp":"2026-10-09T10:01:00Z","alarm_key":"new","asset_id":"pcs_1","action":"raised","severity":"critical","code":"2050.0","payload":{"message":"PCS alarm"}})
        second = run(prod.collect_once())
        assert second["emitted"] is True
        r = payloads(outbox)[0]["records"][0]
        assert FROZEN_S4_FIELDS == set(r)
        assert r["gateway_id"] == cfg.identity.gateway_id and r["site_id"] == cfg.identity.site_id
    finally:
        outbox.close()


def test_s8_baseline_then_config_change_exact_audit_shape(tmp_path):
    cfg = config_for(tmp_path); outbox = OutboxStore(cfg.outbox.path, min_free_space_mb=0)
    gateway_path = Path(cfg.configuration_audit.gateway_config_path); central_path = Path(cfg.configuration_audit.central_sync_config_path)
    gateway_path.write_text(json.dumps({"mode":"mock","bms":{"vendor":"lineage"},"pcs":{"vendor":"elecod","port":502},"control_sequence":{"enabled":True}}))
    central_path.write_text(json.dumps({"enabled":False,"identity":{"software_version":"v0.12"},"backend":{"base_url":"https://example","ingest_path":"/api/v1/ingest/batch","verify_tls":True},"fast_bess":{"poll_interval_sec":1},"general_assets":{},"outbox":{"max_db_size_mb":1024},"command_downlink":{"poll_interval_sec":2}}))
    try:
        prod = ConfigurationAuditProducer(config=cfg, outbox=outbox)
        first = run(prod.collect_once()); assert first["emitted"] is False
        body = json.loads(central_path.read_text()); body["enabled"] = True; central_path.write_text(json.dumps(body))
        second = run(prod.collect_once()); assert second["emitted"] is True
        r = payloads(outbox)[0]["records"][0]
        assert set(r) == {"audit_id","timestamp_utc","gateway_id","site_id","actor","actor_role","change_source","setting_path","old_value","new_value","revision","reason","correlation_id"}
        assert r["setting_path"] == "central_sync.enabled"
    finally:
        outbox.close()


def test_s10_charge_discharge_runtime_and_no_raw_modbus_bypass(tmp_path):
    cfg = config_for(tmp_path); outbox = OutboxStore(cfg.outbox.path, min_free_space_mb=0)
    try:
        result = run(ChargeDischargeProducer(config=cfg, outbox=outbox, local_api=FakeApi()).collect_once(force_emit=True))
        assert result["emitted"] is True
        p = payloads(outbox)[0]; assert p["stream"] == "battery_charge_discharge_control"
        r = p["records"][0]
        assert r["pair_id"] == "pair_1" and r["direction"] == "charge"
        assert r["command_transport"] == "D1 command_requests"
        assert r["result_stream"] == "S9 command_results"
        assert r["raw_modbus_write_bypass"] is False
    finally:
        outbox.close()


def test_d1_routes_pair_command_to_local_api_and_s9_exact_fields(tmp_path):
    cfg = config_for(tmp_path); outbox = OutboxStore(cfg.outbox.path, min_free_space_mb=0); api = FakeApi()
    processor = CommandDownlinkProcessor(config=cfg, outbox=outbox, backend_client=FakeBackend(), local_api=api)
    cmd = {
        "command_id": str(uuid4()), "gateway_id": cfg.identity.gateway_id, "site_id": cfg.identity.site_id,
        "issued_at_utc": "2026-10-09T12:00:00Z", "expires_at_utc": "2099-10-09T12:00:00Z",
        "requested_by": "backend-user", "requested_role": "internal", "command_type": "pair_set_power",
        "arguments": {"pair_id":"pair_1","direction":"discharge","power_kw":20.0}, "requires_readback": True, "priority": "P0", "note": "test",
    }
    try:
        result = run(processor.process_command(cmd)); assert result["final_status"] == "completed"
        assert api.posts and api.posts[0][0] == "/api/control-sequence/pair_1/set-power"
        assert api.posts[0][1]["confirmation"] == cfg.command_downlink.stage_confirmation_phrase
        p = payloads(outbox)[0]
        assert p["stream"] == "command_results" and p["substream"] == "commands"
        r = p["records"][0]
        assert set(r) == FROZEN_S9_FIELDS
        assert r["write_ok"] is True and r["gateway_validation_ok"] is True
    finally:
        run(processor.close()); outbox.close()


def test_d1_duplicate_is_not_executed_twice(tmp_path):
    cfg = config_for(tmp_path); outbox = OutboxStore(cfg.outbox.path, min_free_space_mb=0); api = FakeApi()
    processor = CommandDownlinkProcessor(config=cfg, outbox=outbox, backend_client=FakeBackend(), local_api=api)
    cmd = {
        "command_id": str(uuid4()), "gateway_id": cfg.identity.gateway_id, "site_id": cfg.identity.site_id,
        "issued_at_utc": "2026-10-09T12:00:00Z", "expires_at_utc": "2099-10-09T12:00:00Z",
        "requested_by": "backend-user", "requested_role": "internal", "command_type": "pair_zero_power",
        "arguments": {"pair_id":"pair_1"}, "requires_readback": True,
    }
    try:
        first = run(processor.process_command(cmd)); second = run(processor.process_command(cmd))
        assert first["duplicate"] is False and second["duplicate"] is True
        assert len(api.posts) == 1
    finally:
        run(processor.close()); outbox.close()


def test_d1_invalid_role_rejected_without_local_write_but_with_s9(tmp_path):
    cfg = config_for(tmp_path); outbox = OutboxStore(cfg.outbox.path, min_free_space_mb=0); api = FakeApi()
    processor = CommandDownlinkProcessor(config=cfg, outbox=outbox, backend_client=FakeBackend(), local_api=api)
    cmd = {
        "command_id": str(uuid4()), "gateway_id": cfg.identity.gateway_id, "site_id": cfg.identity.site_id,
        "issued_at_utc": "2026-10-09T12:00:00Z", "expires_at_utc": "2099-10-09T12:00:00Z",
        "requested_by": "customer", "requested_role": "customer", "command_type": "pair_zero_power",
        "arguments": {"pair_id":"pair_1"}, "requires_readback": True,
    }
    try:
        result = run(processor.process_command(cmd)); assert result["final_status"] == "rejected"
        assert api.posts == []
        r = payloads(outbox)[0]["records"][0]
        assert r["gateway_validation_ok"] is False and r["write_ok"] is None
    finally:
        run(processor.close()); outbox.close()
