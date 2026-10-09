from __future__ import annotations

import argparse
import json
import logging
import signal
import time
from typing import Any

from .config import load_uploader_config
from .fast_bess_adapter import FastBESSAdapter
from .frequency_plan import UGXFrequencyPlan
from .full_pcs_bms_adapter import FullPCSBMSAdapter
from .key_mapper import UGXKeyMapper
from .state_store import UploaderStateStore
from .ugx_client import UGXTelemetryClient

LOG = logging.getLogger("nb_ems_gateway.ugx_uploader")
_STOP = False


def _handle_stop(signum: int, frame: Any) -> None:
    global _STOP
    _STOP = True
    LOG.info("stop signal received: %s", signum)


def _chunks(items: list[dict[str, Any]], size: int):
    size = max(1, int(size))
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _payload_bytes(records: list[dict[str, Any]]) -> int:
    return len(json.dumps(records, separators=(",", ":")).encode("utf-8"))


def _map_for_ugx(config, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mapper = UGXKeyMapper(config.ugx_key_mapping)
    return mapper.map_records(records)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="UGX/Uniqgrid cloud telemetry uploader sidecar for Northbound EMS Gateway")
    p.add_argument("--config", default="configs/ugx_cloud_uploader.json")
    p.add_argument("--once", action="store_true", help="run one upload cycle and exit")
    p.add_argument("--dry-run", action="store_true", help="force dry-run mode regardless of config")
    p.add_argument("--live", action="store_true", help="force live POST mode regardless of config")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Existing separated-post upload path retained for rollback/backward compatibility
# ---------------------------------------------------------------------------

def upload_fast_bess(config, state: UploaderStateStore, client: UGXTelemetryClient) -> dict[str, Any]:
    if not config.fast_bess_upload.enabled:
        return {"ok": True, "skipped": True, "reason": "fast_bess_disabled"}
    adapter = FastBESSAdapter(config)
    state_key = f"last_uploaded_epoch_ms:{config.fast_bess_upload.state_key}"
    after_ms = state.get_int(state_key, 0)
    records, max_ts = adapter.fetch_records_after(after_ms)
    if not records:
        return {"ok": True, "records": 0, "last_uploaded_epoch_ms": after_ms}
    records = _map_for_ugx(config, records)
    uploaded = 0
    for batch in _chunks(records, config.fast_bess_upload.max_records_per_post):
        result = client.post_records(batch)
        if not result.get("ok"):
            state.record_run("fast_bess_compact", "failed", "UGX POST failed", result)
            return {"ok": False, "uploaded": uploaded, "error": result}
        uploaded += len(batch)
    state.set_int(state_key, max_ts)
    state.record_run("fast_bess_compact", "ok", f"uploaded {uploaded} timestamped records", {"max_ts": max_ts})
    return {"ok": True, "uploaded_records": uploaded, "last_uploaded_epoch_ms": max_ts}


def upload_full_snapshot_if_due(config, state: UploaderStateStore, client: UGXTelemetryClient) -> dict[str, Any]:
    if not config.full_pcs_bms_upload.enabled:
        return {"ok": True, "skipped": True, "reason": "full_pcs_bms_disabled"}
    now_ms = int(time.time() * 1000)
    state_key = f"last_run_epoch_ms:{config.full_pcs_bms_upload.state_key}"
    last_run_ms = state.get_int(state_key, 0)
    due_ms = int(float(config.full_pcs_bms_upload.interval_sec) * 1000)
    if now_ms - last_run_ms < due_ms:
        return {"ok": True, "skipped": True, "reason": "not_due", "next_due_in_ms": due_ms - (now_ms - last_run_ms)}
    adapter = FullPCSBMSAdapter(config)
    record = adapter.build_snapshot_record()
    records = _map_for_ugx(config, [record])
    record = records[0]
    result = client.post_records(records)
    if not result.get("ok"):
        state.record_run("full_pcs_bms_snapshot", "failed", "UGX POST failed", result)
        return {"ok": False, "error": result}
    state.set_int(state_key, now_ms)
    state.record_run("full_pcs_bms_snapshot", "ok", "uploaded 1 full PCS+BMS snapshot", {"ts": record["ts"], "value_count": len(record["values"])})
    return {"ok": True, "uploaded_records": 1, "value_count": len(record["values"]), "timestamp_epoch_ms": record["ts"]}


def _plan_frequency(config, requested_freq: int) -> int:
    aliases = config.ugx_frequency_upload.frequency_key_aliases or {}
    return int(aliases.get(str(int(requested_freq)), requested_freq))


def _plan_keys_for_frequency(config, plan: UGXFrequencyPlan, requested_freq: int) -> list[str]:
    return plan.keys_for_frequency(_plan_frequency(config, requested_freq))


def _due_frequencies(config, state: UploaderStateStore, plan: UGXFrequencyPlan) -> list[int]:
    now_ms = int(time.time() * 1000)
    due: list[int] = []
    for freq in config.ugx_frequency_upload.enabled_frequencies_sec:
        freq = int(freq)
        plan_freq = _plan_frequency(config, freq)
        if plan_freq == 3600 and not config.ugx_frequency_upload.allow_large_3600_upload:
            continue
        if not _plan_keys_for_frequency(config, plan, freq):
            continue
        key = f"last_run_epoch_ms:{config.ugx_frequency_upload.state_key_prefix}_{freq}s"
        last_ms = state.get_int(key, 0)
        # On first service start, send the profile once immediately. After that, follow the configured interval.
        if last_ms <= 0 or now_ms - last_ms >= freq * 1000:
            due.append(freq)
    return due


def upload_frequency_profiles_if_due(config, state: UploaderStateStore, client: UGXTelemetryClient) -> dict[str, Any]:
    cfg = config.ugx_frequency_upload
    if not cfg.enabled:
        return {"ok": True, "skipped": True, "reason": "ugx_frequency_upload_disabled"}

    plan = UGXFrequencyPlan(cfg.key_plan_path)
    due = _due_frequencies(config, state, plan)
    if not due:
        return {"ok": True, "skipped": True, "reason": "not_due", "enabled_frequencies_sec": cfg.enabled_frequencies_sec}

    adapter = FullPCSBMSAdapter(config)
    mapper = UGXKeyMapper(config.ugx_key_mapping)
    full_record = adapter.build_snapshot_record()
    now_ms = int(time.time() * 1000)

    results: dict[str, Any] = {"ok": True, "profiles": {}}
    for freq in due:
        keys = _plan_keys_for_frequency(config, plan, freq)
        plan_freq = _plan_frequency(config, freq)
        record = mapper.map_record_for_keys(
            full_record,
            keys,
            include_null_keys=cfg.include_null_keys,
            always_include_time_fields=cfg.always_include_time_fields,
        )
        value_count = len(record.get("values") or {})
        if value_count <= 0 and not cfg.post_empty_profiles:
            results["profiles"][str(freq)] = {"ok": True, "skipped": True, "reason": "empty_profile", "planned_key_count": len(keys), "plan_frequency_sec": plan_freq}
            continue
        if value_count > int(cfg.max_keys_per_post):
            result = {"ok": False, "error": "max_keys_per_post_exceeded", "value_count": value_count, "max_keys_per_post": cfg.max_keys_per_post, "planned_key_count": len(keys), "plan_frequency_sec": plan_freq}
            state.record_run(f"ugx_frequency_{freq}s", "failed", "max keys exceeded", result)
            results["ok"] = False
            results["profiles"][str(freq)] = result
            continue
        post_result = client.post_records([record])
        if not post_result.get("ok"):
            state.record_run(f"ugx_frequency_{freq}s", "failed", "UGX POST failed", post_result)
            results["ok"] = False
            results["profiles"][str(freq)] = {"ok": False, "error": post_result, "value_count": value_count, "planned_key_count": len(keys), "plan_frequency_sec": plan_freq}
            continue
        state_key = f"last_run_epoch_ms:{cfg.state_key_prefix}_{freq}s"
        state.set_int(state_key, now_ms)
        state.record_run(
            f"ugx_frequency_{freq}s",
            "ok",
            f"uploaded 1 UGX {freq}s frequency record",
            {"ts": record["ts"], "value_count": value_count, "planned_key_count": len(keys), "plan_frequency_sec": plan_freq},
        )
        results["profiles"][str(freq)] = {"ok": True, "uploaded_records": 1, "value_count": value_count, "planned_key_count": len(keys), "timestamp_epoch_ms": record["ts"], "plan_frequency_sec": plan_freq}
    return results


# ---------------------------------------------------------------------------
# U1.3 combined-post upload path
# ---------------------------------------------------------------------------

def _combined_cloud_due(config, state: UploaderStateStore) -> tuple[bool, int, int]:
    now_ms = int(time.time() * 1000)
    state_key = f"last_run_epoch_ms:{config.ugx_combined_upload.state_key}"
    last_ms = state.get_int(state_key, 0)
    interval_ms = int(float(config.ugx_combined_upload.cloud_post_interval_sec) * 1000)
    if last_ms <= 0:
        return True, now_ms, 0
    return (now_ms - last_ms >= interval_ms), now_ms, last_ms


def _collect_fast_bess_for_combined(config, state: UploaderStateStore) -> tuple[list[dict[str, Any]], dict[str, Any], int | None]:
    if not config.fast_bess_upload.enabled or not config.ugx_combined_upload.include_fast_bess:
        return [], {"ok": True, "skipped": True, "reason": "fast_bess_disabled_or_not_included"}, None
    adapter = FastBESSAdapter(config)
    state_key = f"last_uploaded_epoch_ms:{config.fast_bess_upload.state_key}"
    after_ms = state.get_int(state_key, 0)
    records, max_ts = adapter.fetch_records_after(after_ms)
    if not records:
        return [], {"ok": True, "records": 0, "last_uploaded_epoch_ms": after_ms}, None
    records = _map_for_ugx(config, records)
    return records, {"ok": True, "pending_records": len(records), "max_ts": max_ts, "last_uploaded_epoch_ms": after_ms}, max_ts


def _collect_frequency_for_combined(config, state: UploaderStateStore) -> tuple[list[dict[str, Any]], dict[str, Any], dict[int, int]]:
    cfg = config.ugx_frequency_upload
    if not cfg.enabled or not config.ugx_combined_upload.include_frequency_profiles:
        return [], {"ok": True, "skipped": True, "reason": "ugx_frequency_disabled_or_not_included"}, {}

    plan = UGXFrequencyPlan(cfg.key_plan_path)
    due = _due_frequencies(config, state, plan)
    if not due:
        return [], {"ok": True, "skipped": True, "reason": "not_due", "enabled_frequencies_sec": cfg.enabled_frequencies_sec}, {}

    adapter = FullPCSBMSAdapter(config)
    mapper = UGXKeyMapper(config.ugx_key_mapping)
    full_record = adapter.build_snapshot_record()
    now_ms = int(time.time() * 1000)

    records: list[dict[str, Any]] = []
    due_state_updates: dict[int, int] = {}
    results: dict[str, Any] = {"ok": True, "profiles": {}}
    for freq in due:
        keys = _plan_keys_for_frequency(config, plan, freq)
        plan_freq = _plan_frequency(config, freq)
        record = mapper.map_record_for_keys(
            full_record,
            keys,
            include_null_keys=cfg.include_null_keys,
            always_include_time_fields=cfg.always_include_time_fields,
        )
        value_count = len(record.get("values") or {})
        if value_count <= 0 and not cfg.post_empty_profiles:
            results["profiles"][str(freq)] = {"ok": True, "skipped": True, "reason": "empty_profile", "planned_key_count": len(keys), "plan_frequency_sec": plan_freq}
            continue
        if value_count > int(cfg.max_keys_per_post):
            result = {"ok": False, "error": "max_keys_per_post_exceeded", "value_count": value_count, "max_keys_per_post": cfg.max_keys_per_post, "planned_key_count": len(keys), "plan_frequency_sec": plan_freq}
            results["ok"] = False
            results["profiles"][str(freq)] = result
            continue
        records.append(record)
        due_state_updates[int(freq)] = now_ms
        results["profiles"][str(freq)] = {"ok": True, "pending_records": 1, "value_count": value_count, "planned_key_count": len(keys), "timestamp_epoch_ms": record["ts"], "plan_frequency_sec": plan_freq}
    return records, results, due_state_updates


def upload_combined_if_due(config, state: UploaderStateStore, client: UGXTelemetryClient) -> dict[str, Any]:
    cfg = config.ugx_combined_upload
    if not cfg.enabled:
        return {"ok": True, "skipped": True, "reason": "ugx_combined_upload_disabled"}

    due, now_ms, last_ms = _combined_cloud_due(config, state)
    if not due:
        next_due_ms = int(float(cfg.cloud_post_interval_sec) * 1000) - (now_ms - last_ms)
        return {"ok": True, "skipped": True, "reason": "combined_not_due", "next_due_in_ms": max(0, next_due_ms), "cloud_post_interval_sec": cfg.cloud_post_interval_sec}

    fast_records, fast_result, fast_max_ts = _collect_fast_bess_for_combined(config, state)
    freq_records, freq_result, freq_state_updates = _collect_frequency_for_combined(config, state)
    combined_records = fast_records + freq_records

    if not combined_records:
        state.set_int(f"last_run_epoch_ms:{cfg.state_key}", now_ms)
        return {"ok": True, "skipped": True, "reason": "no_due_records", "fast_bess": fast_result, "ugx_frequency": freq_result}

    payload_bytes = _payload_bytes(combined_records)
    if len(combined_records) > int(cfg.max_records_per_post):
        result = {"ok": False, "error": "max_combined_records_exceeded", "records": len(combined_records), "max_records_per_post": cfg.max_records_per_post, "payload_bytes": payload_bytes}
        state.record_run(cfg.record_profile, "failed", "combined record count exceeded", result)
        return {"ok": False, "fast_bess": fast_result, "ugx_frequency": freq_result, "combined_post": result}
    if payload_bytes > int(cfg.max_payload_bytes):
        result = {"ok": False, "error": "max_combined_payload_bytes_exceeded", "records": len(combined_records), "payload_bytes": payload_bytes, "max_payload_bytes": cfg.max_payload_bytes}
        state.record_run(cfg.record_profile, "failed", "combined payload size exceeded", result)
        return {"ok": False, "fast_bess": fast_result, "ugx_frequency": freq_result, "combined_post": result}

    post_result = client.post_records(combined_records)
    if not post_result.get("ok"):
        state.record_run(cfg.record_profile, "failed", "UGX combined POST failed", post_result)
        return {"ok": False, "fast_bess": fast_result, "ugx_frequency": freq_result, "combined_post": post_result}

    # Advance all state pointers only after a real successful cloud POST.
    # Dry-run validation intentionally does not advance pointers, so live mode
    # will still send the same pending data after validation.
    state_was_committed = False
    if not post_result.get("dry_run"):
        if fast_max_ts is not None:
            state.set_int(f"last_uploaded_epoch_ms:{config.fast_bess_upload.state_key}", int(fast_max_ts))
            state.record_run("fast_bess_compact", "ok", f"included {len(fast_records)} fast records in combined POST", {"max_ts": fast_max_ts})
        for freq, state_ms in freq_state_updates.items():
            state_key = f"last_run_epoch_ms:{config.ugx_frequency_upload.state_key_prefix}_{freq}s"
            state.set_int(state_key, state_ms)
            profile = (freq_result.get("profiles") or {}).get(str(freq), {}) if isinstance(freq_result, dict) else {}
            state.record_run(f"ugx_frequency_{freq}s", "ok", f"included UGX {freq}s record in combined POST", profile)
        state.set_int(f"last_run_epoch_ms:{cfg.state_key}", now_ms)
        state.record_run(
            cfg.record_profile,
            "ok",
            "uploaded one combined UGX POST",
            {
                "records": len(combined_records),
                "payload_bytes": payload_bytes,
                "fast_records": len(fast_records),
                "frequency_records": len(freq_records),
                "frequency_profiles": list((freq_result.get("profiles") or {}).keys()) if isinstance(freq_result, dict) else [],
                "url": post_result.get("url"),
            },
        )
        state_was_committed = True
    else:
        state.record_run(
            cfg.record_profile,
            "dry_run",
            "validated one combined UGX POST without advancing pointers",
            {
                "records": len(combined_records),
                "payload_bytes": payload_bytes,
                "fast_records": len(fast_records),
                "frequency_records": len(freq_records),
                "frequency_profiles": list((freq_result.get("profiles") or {}).keys()) if isinstance(freq_result, dict) else [],
                "url": post_result.get("url"),
            },
        )

    combined_summary = {
        "ok": True,
        "single_cloud_post": True,
        "uploaded_records": len(combined_records),
        "payload_bytes": payload_bytes,
        "cloud_post_interval_sec": cfg.cloud_post_interval_sec,
        "state_committed": state_was_committed,
        "post_result": {k: v for k, v in post_result.items() if k in {"status_code", "records", "payload_bytes", "url", "dry_run"}},
    }
    return {"ok": True, "fast_bess": fast_result, "ugx_frequency": freq_result, "combined_post": combined_summary}


def run_separated_cycle(config, state: UploaderStateStore, client: UGXTelemetryClient) -> dict[str, Any]:
    results: dict[str, Any] = {}
    try:
        results["fast_bess"] = upload_fast_bess(config, state, client)
    except Exception as exc:
        LOG.exception("fast BESS upload cycle failed")
        results["fast_bess"] = {"ok": False, "error": str(exc)}
        state.record_run("fast_bess_compact", "exception", str(exc))
    try:
        results["full_pcs_bms"] = upload_full_snapshot_if_due(config, state, client)
    except Exception as exc:
        LOG.exception("full PCS/BMS upload cycle failed")
        results["full_pcs_bms"] = {"ok": False, "error": str(exc)}
        state.record_run("full_pcs_bms_snapshot", "exception", str(exc))
    try:
        results["ugx_frequency"] = upload_frequency_profiles_if_due(config, state, client)
    except Exception as exc:
        LOG.exception("UGX frequency profile upload cycle failed")
        results["ugx_frequency"] = {"ok": False, "error": str(exc)}
        state.record_run("ugx_frequency", "exception", str(exc))
    return results


def run_cycle(config, state: UploaderStateStore, client: UGXTelemetryClient) -> dict[str, Any]:
    if config.ugx_combined_upload.enabled:
        try:
            return {"ugx_combined": upload_combined_if_due(config, state, client)}
        except Exception as exc:
            LOG.exception("UGX combined upload cycle failed")
            state.record_run("ugx_combined", "exception", str(exc))
            return {"ugx_combined": {"ok": False, "error": str(exc)}}
    return run_separated_cycle(config, state, client)


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    config = load_uploader_config(args.config)
    if args.dry_run:
        config.dry_run = True
    if args.live:
        config.dry_run = False
    LOG.info(
        "UGX uploader starting enabled=%s dry_run=%s url=%s combined_enabled=%s combined_interval_sec=%s",
        config.enabled,
        config.dry_run,
        config.ugx_server.telemetry_url,
        config.ugx_combined_upload.enabled,
        config.ugx_combined_upload.cloud_post_interval_sec,
    )
    if not config.enabled:
        LOG.warning("UGX uploader disabled by config")
        return
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    state = UploaderStateStore(config.state_db_path)
    client = UGXTelemetryClient(config.ugx_server, dry_run=config.dry_run)
    try:
        while not _STOP:
            results = run_cycle(config, state, client)
            if config.log_payload_preview:
                LOG.info("cycle result: %s", json.dumps(results, separators=(",", ":"))[:3000])
            if args.once:
                print(json.dumps(results, indent=2))
                break
            sleep_sec = config.run_interval_sec
            if any(isinstance(v, dict) and not v.get("ok", True) for v in results.values()):
                sleep_sec = max(sleep_sec, config.failed_retry_interval_sec)
            end = time.time() + float(sleep_sec)
            while not _STOP and time.time() < end:
                time.sleep(0.5)
    finally:
        state.close()
        LOG.info("UGX uploader stopped")


if __name__ == "__main__":
    main()
