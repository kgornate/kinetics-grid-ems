from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from .client import CentralBackendClient
from .config import CentralSyncConfig
from .contracts import make_message, utc_now_iso
from .local_gateway_api import LocalGatewayApiClient, LocalGatewayApiError
from .outbox import OutboxCapacityError, OutboxStore
from .status import safe_write_json

log = logging.getLogger(__name__)

TERMINAL_STATES = {"rejected", "completed", "failed", "timeout"}


@dataclass
class CommandDownlinkCounters:
    poll_count: int = 0
    poll_success_count: int = 0
    poll_failure_count: int = 0
    commands_received: int = 0
    duplicate_count: int = 0
    validation_rejected_count: int = 0
    execution_started_count: int = 0
    execution_completed_count: int = 0
    execution_failed_count: int = 0
    s9_enqueued_count: int = 0
    s9_enqueue_failure_count: int = 0
    last_poll_utc: str | None = None
    last_success_utc: str | None = None
    last_error: str | None = None
    last_command_id: str | None = None
    last_command_type: str | None = None
    last_final_status: str | None = None
    last_s9_sequence: int | None = None
    last_s9_message_id: str | None = None


class CommandLedger:
    """Small persistent idempotency/recovery ledger for D1.

    This is intentionally separate from the proven telemetry outbox schema.  It
    provides duplicate suppression across process restarts without changing
    outbox.py/uploader.py or any existing stream sequence.
    """

    def __init__(self, path: str) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, timeout=30.0, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self.conn:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=FULL")
            self.conn.execute("PRAGMA busy_timeout=30000")
            self.conn.execute(
                """CREATE TABLE IF NOT EXISTS command_ledger(
                    command_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    command_json TEXT NOT NULL,
                    result_json TEXT,
                    received_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    s9_message_id TEXT,
                    s9_sequence INTEGER
                )"""
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_command_ledger_state ON command_ledger(state)"
            )

    def claim(self, command_id: str, command: dict[str, Any], received_at_utc: str) -> bool:
        now = utc_now_iso()
        payload = json.dumps(command, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
        with self._lock:
            try:
                with self.conn:
                    self.conn.execute(
                        """INSERT INTO command_ledger(
                            command_id,state,command_json,received_at_utc,updated_at_utc
                        ) VALUES(?,?,?,?,?)""",
                        (command_id, "received", payload, received_at_utc, now),
                    )
                return True
            except sqlite3.IntegrityError:
                return False

    def get(self, command_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM command_ledger WHERE command_id=?", (command_id,)
            ).fetchone()
        return dict(row) if row else None

    def set_state(self, command_id: str, state: str) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                "UPDATE command_ledger SET state=?,updated_at_utc=? WHERE command_id=?",
                (state, utc_now_iso(), command_id),
            )

    def store_result(self, command_id: str, result: dict[str, Any], *, state: str = "s9_pending") -> None:
        with self._lock, self.conn:
            self.conn.execute(
                """UPDATE command_ledger
                   SET state=?,result_json=?,updated_at_utc=?
                   WHERE command_id=?""",
                (
                    state,
                    json.dumps(result, separators=(",", ":"), sort_keys=True, ensure_ascii=False),
                    utc_now_iso(),
                    command_id,
                ),
            )

    def mark_s9_durable(self, command_id: str, final_status: str, message_id: str, sequence: int) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                """UPDATE command_ledger
                   SET state=?,s9_message_id=?,s9_sequence=?,updated_at_utc=?
                   WHERE command_id=?""",
                (final_status, message_id, int(sequence), utc_now_iso(), command_id),
            )

    def pending_results(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM command_ledger WHERE state='s9_pending' ORDER BY received_at_utc"
            ).fetchall()
        return [dict(r) for r in rows]

    def uncertain_incomplete(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.conn.execute(
                """SELECT * FROM command_ledger
                   WHERE state IN ('received','executing')
                   ORDER BY received_at_utc"""
            ).fetchall()
        return [dict(r) for r in rows]

    def counts(self) -> dict[str, int]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT state,COUNT(*) AS n FROM command_ledger GROUP BY state"
            ).fetchall()
        return {str(r["state"]): int(r["n"]) for r in rows}

    def close(self) -> None:
        with self._lock:
            self.conn.close()


class CommandDownlinkProcessor:
    """D1 command poller + local safety boundary + S9 result producer."""

    def __init__(
        self,
        *,
        config: CentralSyncConfig,
        outbox: OutboxStore,
        backend_client: CentralBackendClient | Any | None = None,
        local_api: LocalGatewayApiClient | Any | None = None,
        ledger: CommandLedger | Any | None = None,
    ) -> None:
        self.config = config
        self.command_config = config.command_downlink
        self.outbox = outbox
        self.backend = backend_client or CentralBackendClient(config.backend, config.identity.gateway_id)
        self.local_api = local_api or LocalGatewayApiClient(config.local_gateway_api)
        self.ledger = ledger or CommandLedger(self.command_config.ledger_path)
        self._owns_backend = backend_client is None
        self._owns_local = local_api is None
        self._owns_ledger = ledger is None
        self.counters = CommandDownlinkCounters()
        self.running = False
        self.started_utc = utc_now_iso()
        self._stop = asyncio.Event()
        self._recovery_done = False

    async def close(self) -> None:
        if self._owns_backend:
            await self.backend.close()
        if self._owns_local:
            await self.local_api.close()
        if self._owns_ledger:
            await asyncio.to_thread(self.ledger.close)

    async def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        if not self.command_config.enabled:
            log.info("D1 command downlink disabled")
            return
        self.running = True
        self._stop.clear()
        await self.recover_once()
        log.info(
            "D1 command downlink started poll=%.1fs path=%s",
            self.command_config.poll_interval_sec,
            self.command_config.poll_path,
        )
        try:
            while not self._stop.is_set():
                await self.poll_once()
                try:
                    await asyncio.wait_for(
                        self._stop.wait(),
                        timeout=max(0.2, self.command_config.poll_interval_sec),
                    )
                except asyncio.TimeoutError:
                    pass
        finally:
            self.running = False
            self._write_status()
            log.info("D1 command downlink stopped")

    async def recover_once(self) -> None:
        if self._recovery_done:
            return
        self._recovery_done = True

        # First retry terminal results that were already decided but not yet durable
        # in the telemetry outbox because of a capacity/crash window.
        for row in await asyncio.to_thread(self.ledger.pending_results):
            try:
                result = json.loads(row.get("result_json") or "{}")
                if isinstance(result, dict) and result:
                    await self._enqueue_s9(str(row["command_id"]), result)
            except Exception as exc:
                log.warning("D1 recovery could not re-enqueue pending S9 %s: %s", row.get("command_id"), exc)

        # An execution interrupted by a process crash is deliberately not replayed.
        # Remote power commands must fail safe rather than risk a duplicate write.
        for row in await asyncio.to_thread(self.ledger.uncertain_incomplete):
            try:
                cmd = json.loads(row.get("command_json") or "{}")
            except Exception:
                cmd = {}
            result = self._result_base(cmd, received_at_utc=str(row.get("received_at_utc") or utc_now_iso()))
            result.update(
                gateway_validation_ok=False,
                validation_reason="previous command lifecycle interrupted by gateway restart; not re-executed",
                execution_started_at_utc=None,
                execution_finished_at_utc=utc_now_iso(),
                write_ok=None,
                readback_value=None,
                verified=None,
                final_status="failed",
                failure_reason="execution state uncertain after restart",
                gateway_error_code="COMMAND_RECOVERY_UNCERTAIN",
                duration_ms=None,
            )
            await asyncio.to_thread(self.ledger.store_result, str(row["command_id"]), result)
            await self._enqueue_s9(str(row["command_id"]), result)

    async def poll_once(self) -> dict[str, Any]:
        now = utc_now_iso()
        self.counters.poll_count += 1
        self.counters.last_poll_utc = now
        response = await self.backend.get_json(
            self.command_config.poll_path,
            params={
                "gateway_id": self.config.identity.gateway_id,
                "site_id": self.config.identity.site_id,
                "limit": self.command_config.max_commands_per_poll,
            },
        )
        if response.status_code == 204:
            self.counters.poll_success_count += 1
            self.counters.last_success_utc = now
            self.counters.last_error = None
            self._write_status()
            return {"received": 0, "processed": 0, "http_status": 204}
        if not response.ok:
            self.counters.poll_failure_count += 1
            self.counters.last_error = response.exception or f"HTTP {response.status_code}: {response.text[:300]}"
            self._write_status()
            log.warning("D1 poll failed: %s", self.counters.last_error)
            return {"received": 0, "processed": 0, "http_status": response.status_code, "error": self.counters.last_error}
        body = response.body or {}
        commands = body.get("commands", []) if isinstance(body, dict) else []
        if not isinstance(commands, list):
            self.counters.poll_failure_count += 1
            self.counters.last_error = "D1 poll response 'commands' must be an array"
            self._write_status()
            return {"received": 0, "processed": 0, "error": self.counters.last_error}
        self.counters.poll_success_count += 1
        self.counters.last_success_utc = now
        self.counters.last_error = None
        processed = 0
        for command in commands[: self.command_config.max_commands_per_poll]:
            if not isinstance(command, dict):
                continue
            await self.process_command(command)
            processed += 1
        self._write_status()
        return {"received": len(commands), "processed": processed, "http_status": response.status_code}

    async def process_command(self, command: dict[str, Any], *, forbid_execution: bool = False) -> dict[str, Any]:
        received_at = utc_now_iso()
        self.counters.commands_received += 1
        command_id = str(command.get("command_id") or "").strip()
        self.counters.last_command_id = command_id or None
        self.counters.last_command_type = str(command.get("command_type") or "") or None

        # Invalid/missing command_id cannot be safely deduplicated.  Still return a
        # local result to the manual test caller, but do not invent an S9 identity.
        if not _valid_uuid(command_id):
            self.counters.validation_rejected_count += 1
            self.counters.last_final_status = "rejected"
            self.counters.last_error = "invalid or missing command_id"
            self._write_status()
            return {"accepted": False, "duplicate": False, "error": "INVALID_COMMAND_ID", "s9_enqueued": False}

        claimed = await asyncio.to_thread(self.ledger.claim, command_id, command, received_at)
        if not claimed:
            self.counters.duplicate_count += 1
            existing = await asyncio.to_thread(self.ledger.get, command_id)
            # If the result was decided but not durable, retry only the S9 enqueue;
            # never execute the field command twice.
            if existing and existing.get("state") == "s9_pending" and existing.get("result_json"):
                try:
                    result = json.loads(existing["result_json"])
                    await self._enqueue_s9(command_id, result)
                except Exception as exc:
                    self.counters.last_error = f"duplicate S9 recovery failed: {exc}"
            self._write_status()
            return {"accepted": False, "duplicate": True, "state": existing.get("state") if existing else None}

        validation = self._validate(command, forbid_execution=forbid_execution)
        if validation is not None:
            code, reason = validation
            self.counters.validation_rejected_count += 1
            result = self._result_base(command, received_at_utc=received_at)
            result.update(
                gateway_validation_ok=False,
                validation_reason=reason,
                execution_started_at_utc=None,
                execution_finished_at_utc=utc_now_iso(),
                write_ok=None,
                readback_value=None,
                verified=None,
                final_status="rejected",
                failure_reason=reason,
                gateway_error_code=code,
                duration_ms=None,
            )
            await asyncio.to_thread(self.ledger.store_result, command_id, result)
            s9 = await self._enqueue_s9(command_id, result)
            self.counters.last_final_status = "rejected"
            self._write_status()
            return {"accepted": False, "duplicate": False, "validation_code": code, "s9_enqueued": s9}

        self.counters.execution_started_count += 1
        await asyncio.to_thread(self.ledger.set_state, command_id, "executing")
        start_iso = utc_now_iso()
        start = time.monotonic()
        try:
            path, body = self._route(command)
            response = await self.local_api.post_json(path, body)
            duration_ms = (time.monotonic() - start) * 1000.0
            ok = bool(response.get("ok", True))
            requires_readback = bool(command.get("requires_readback"))
            result = self._result_base(command, received_at_utc=received_at)
            result.update(
                gateway_validation_ok=True,
                validation_reason="accepted by gateway validation",
                execution_started_at_utc=start_iso,
                execution_finished_at_utc=utc_now_iso(),
                write_ok=ok,
                readback_value=response if requires_readback else None,
                verified=(ok if requires_readback else None),
                final_status=("completed" if ok else "failed"),
                failure_reason=(None if ok else str(response.get("error") or "local control returned ok=false")),
                gateway_error_code=(None if ok else "LOCAL_CONTROL_REPORTED_FAILURE"),
                duration_ms=round(duration_ms, 3),
            )
            if ok:
                self.counters.execution_completed_count += 1
            else:
                self.counters.execution_failed_count += 1
        except Exception as exc:
            duration_ms = (time.monotonic() - start) * 1000.0
            self.counters.execution_failed_count += 1
            result = self._result_base(command, received_at_utc=received_at)
            result.update(
                gateway_validation_ok=True,
                validation_reason="accepted by gateway validation",
                execution_started_at_utc=start_iso,
                execution_finished_at_utc=utc_now_iso(),
                write_ok=False,
                readback_value=None,
                verified=False if bool(command.get("requires_readback")) else None,
                final_status="failed",
                failure_reason=f"{type(exc).__name__}: {exc}",
                gateway_error_code=("LOCAL_API_ERROR" if isinstance(exc, LocalGatewayApiError) else "COMMAND_EXECUTION_ERROR"),
                duration_ms=round(duration_ms, 3),
            )

        await asyncio.to_thread(self.ledger.store_result, command_id, result)
        s9 = await self._enqueue_s9(command_id, result)
        self.counters.last_final_status = str(result["final_status"])
        self._write_status()
        return {"accepted": True, "duplicate": False, "final_status": result["final_status"], "s9_enqueued": s9}

    def _validate(self, command: dict[str, Any], *, forbid_execution: bool) -> tuple[str, str] | None:
        required = [
            "gateway_id", "site_id", "issued_at_utc", "expires_at_utc",
            "requested_by", "requested_role", "command_type", "arguments",
            "requires_readback", "priority",
        ]
        missing = [k for k in required if k not in command]
        if missing:
            return "D1_SCHEMA_INVALID", "missing required fields: " + ", ".join(missing)
        if str(command.get("gateway_id")) != self.config.identity.gateway_id:
            return "TARGET_GATEWAY_MISMATCH", "command gateway_id does not match this gateway"
        if str(command.get("site_id")) != self.config.identity.site_id:
            return "TARGET_SITE_MISMATCH", "command site_id does not match this site"
        if str(command.get("requested_role")) != self.command_config.allowed_requested_role:
            return "ROLE_NOT_ALLOWED", f"requested_role must be {self.command_config.allowed_requested_role}"
        ctype = str(command.get("command_type") or "")
        if ctype not in set(self.command_config.allowed_command_types):
            return "COMMAND_TYPE_NOT_ALLOWED", f"command_type {ctype!r} is not in the gateway allowlist"
        if not isinstance(command.get("arguments"), dict):
            return "ARGUMENTS_INVALID", "arguments must be a JSON object"
        issued = _parse_utc(command.get("issued_at_utc"))
        expires = _parse_utc(command.get("expires_at_utc"))
        if issued is None or expires is None:
            return "TIMESTAMP_INVALID", "issued_at_utc/expires_at_utc must be valid UTC datetimes"
        if expires <= issued:
            return "EXPIRY_INVALID", "expires_at_utc must be after issued_at_utc"
        if datetime.now(timezone.utc) >= expires:
            return "COMMAND_EXPIRED", "command expired before gateway execution"
        arg_error = self._validate_arguments(ctype, command["arguments"])
        if arg_error:
            return "ARGUMENTS_INVALID", arg_error
        if forbid_execution:
            return "TEST_EXECUTION_DISABLED", "manual commissioning injection forbids field execution"
        return None

    def _validate_arguments(self, ctype: str, a: dict[str, Any]) -> str | None:
        source_types = {"source_grid_mode", "source_charge", "source_discharge", "source_standby"}
        if ctype in source_types and not str(a.get("source_id") or "").strip():
            return "source_id is required for source command"
        if ctype in {"source_grid_mode", "site_grid_mode"} and a.get("target_mode") not in {"grid_tied", "off_grid"}:
            return "target_mode must be grid_tied or off_grid"
        if ctype in {"source_charge", "source_discharge"}:
            try:
                if float(a.get("power_kw")) <= 0:
                    return "power_kw must be > 0"
            except Exception:
                return "power_kw must be numeric and > 0"
        if ctype == "site_power":
            if a.get("operation") not in {"charge", "discharge"}:
                return "operation must be charge or discharge"
            try:
                if float(a.get("total_power_kw")) <= 0:
                    return "total_power_kw must be > 0"
            except Exception:
                return "total_power_kw must be numeric and > 0"
            if a.get("allocation", "equal") not in {"equal", "custom"}:
                return "allocation must be equal or custom"
        if ctype == "ems_register_write":
            if not str(a.get("source_id") or "").strip():
                return "source_id is required"
            if a.get("signal_name") is None and a.get("address") is None:
                return "signal_name or address is required"
            if a.get("value") is None:
                return "value is required"
        if ctype == "ems_batch_write":
            writes = a.get("writes")
            if not isinstance(writes, list) or not writes:
                return "writes must be a non-empty array"
        return None

    def _route(self, command: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        ctype = str(command["command_type"])
        a = dict(command.get("arguments") or {})
        readback = bool(command.get("requires_readback"))
        note = command.get("note")
        if note is not None and "note" not in a:
            a["note"] = note
        if ctype == "source_grid_mode":
            source_id = str(a.pop("source_id"))
            a["readback"] = readback
            return f"/api/control/sources/{source_id}/grid-mode", a
        if ctype == "site_grid_mode":
            a["readback"] = readback
            return "/api/control/site/grid-mode", a
        if ctype == "source_charge":
            source_id = str(a.pop("source_id"))
            a["readback"] = readback
            return f"/api/control/sources/{source_id}/charge", a
        if ctype == "source_discharge":
            source_id = str(a.pop("source_id"))
            a["readback"] = readback
            return f"/api/control/sources/{source_id}/discharge", a
        if ctype == "source_standby":
            source_id = str(a.pop("source_id"))
            a["readback"] = readback
            return f"/api/control/sources/{source_id}/standby", a
        if ctype == "site_power":
            a["readback"] = readback
            return "/api/control/site/power", a
        if ctype == "site_standby":
            a["readback"] = readback
            return "/api/control/site/standby", a
        if ctype == "ems_register_write":
            a["readback"] = readback
            return "/api/commands/ems/write", a
        if ctype == "ems_batch_write":
            # Individual writes retain their own readback if explicitly supplied;
            # otherwise inherit the D1 requires_readback policy.
            for item in a.get("writes", []):
                if isinstance(item, dict):
                    item.setdefault("readback", readback)
            return "/api/commands/ems/batch", a
        raise ValueError(f"unsupported command type: {ctype}")

    def _result_base(self, command: dict[str, Any], *, received_at_utc: str) -> dict[str, Any]:
        args = command.get("arguments") if isinstance(command.get("arguments"), dict) else {}
        ctype = str(command.get("command_type") or "")
        source_id = args.get("source_id")
        signal_name = args.get("signal_name") if ctype == "ems_register_write" else None
        return {
            "command_id": str(command.get("command_id") or ""),
            "correlation_id": str(command.get("correlation_id") or command.get("command_id") or "") or None,
            "gateway_id": self.config.identity.gateway_id,
            "site_id": self.config.identity.site_id,
            "requested_at_utc": str(command.get("issued_at_utc") or ""),
            "received_at_utc": received_at_utc,
            "requested_by": str(command.get("requested_by") or ""),
            "requested_role": str(command.get("requested_role") or ""),
            "command_type": ctype,
            "source_id": str(source_id) if source_id is not None else None,
            "asset_id": args.get("asset_id"),
            "signal_name": str(signal_name) if signal_name is not None else None,
            "requested_value": args,
            "gateway_validation_ok": False,
            "validation_reason": None,
            "execution_started_at_utc": None,
            "execution_finished_at_utc": None,
            "write_ok": None,
            "readback_requested": bool(command.get("requires_readback")),
            "readback_value": None,
            "verified": None,
            "final_status": "rejected",
            "failure_reason": None,
            "gateway_error_code": None,
            "duration_ms": None,
            "note": command.get("note"),
        }

    async def _enqueue_s9(self, command_id: str, result: dict[str, Any]) -> bool:
        message_id = str(uuid5(NAMESPACE_URL, f"ornate-central-sync:s9:{command_id}:final"))
        sequence = await asyncio.to_thread(
            self.outbox.next_sequence,
            self.command_config.s9_stream,
            self.command_config.s9_substream,
        )
        message = make_message(
            schema_version=self.config.identity.schema_version,
            gateway_id=self.config.identity.gateway_id,
            site_id=self.config.identity.site_id,
            stream=self.command_config.s9_stream,
            substream=self.command_config.s9_substream,
            sequence=sequence,
            priority=self.command_config.s9_priority,
            records=[result],
            created_at_utc=str(result.get("execution_finished_at_utc") or result.get("received_at_utc") or utc_now_iso()),
            message_id=message_id,
        )
        try:
            inserted = await asyncio.to_thread(self.outbox.enqueue, message)
        except OutboxCapacityError as exc:
            self.counters.s9_enqueue_failure_count += 1
            self.counters.last_error = f"S9 outbox capacity backpressure: {exc}"
            log.error("S9 enqueue blocked by outbox capacity: %s", exc)
            return False
        except Exception as exc:
            self.counters.s9_enqueue_failure_count += 1
            self.counters.last_error = f"S9 enqueue failed: {type(exc).__name__}: {exc}"
            log.exception("S9 enqueue failed")
            return False

        # inserted=False means the deterministic final result is already durable.
        # Mark terminal either way; duplicate D1 delivery must never re-execute.
        await asyncio.to_thread(
            self.ledger.mark_s9_durable,
            command_id,
            str(result.get("final_status") or "failed"),
            message_id,
            sequence,
        )
        self.counters.s9_enqueued_count += 1
        self.counters.last_s9_sequence = sequence
        self.counters.last_s9_message_id = message_id
        return bool(inserted or not inserted)

    def status(self) -> dict[str, Any]:
        try:
            ledger_counts = self.ledger.counts()
        except Exception:
            ledger_counts = {}
        return {
            "enabled": self.command_config.enabled,
            "running": self.running,
            "started_utc": self.started_utc,
            "poll_path": self.command_config.poll_path,
            "poll_interval_sec": self.command_config.poll_interval_sec,
            "max_commands_per_poll": self.command_config.max_commands_per_poll,
            "s9_stream": self.command_config.s9_stream,
            "s9_substream": self.command_config.s9_substream,
            "ledger_path": self.command_config.ledger_path,
            "ledger_counts": ledger_counts,
            "counters": self.counters.__dict__.copy(),
            "status_generated_utc": utc_now_iso(),
        }

    def _write_status(self) -> None:
        try:
            safe_write_json(self.command_config.status_file, self.status())
        except Exception as exc:
            log.warning("D1 status write failed: %s", exc)


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc)


def _valid_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except Exception:
        return False
