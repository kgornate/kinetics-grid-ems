from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from .client import CentralBackendClient
from .config import CentralSyncConfig
from .contracts import utc_now_iso
from .local_gateway_api import LocalGatewayApiClient
from .outbox import OutboxStore
from .producer_common import emit_message
from .status import safe_write_json

TERMINAL_STATES = {"rejected", "completed", "failed", "timeout"}


class CommandLedger:
    """Persistent D1 idempotency ledger copied from the Northbound design."""
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
            self.conn.execute("""CREATE TABLE IF NOT EXISTS command_ledger(
                command_id TEXT PRIMARY KEY, state TEXT NOT NULL, command_json TEXT NOT NULL,
                result_json TEXT, received_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL,
                s9_message_id TEXT, s9_sequence INTEGER)""")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_command_ledger_state ON command_ledger(state)")

    def claim(self, command_id: str, command: dict[str, Any], received: str) -> bool:
        with self._lock:
            try:
                with self.conn:
                    self.conn.execute(
                        "INSERT INTO command_ledger(command_id,state,command_json,received_at_utc,updated_at_utc) VALUES(?,?,?,?,?)",
                        (command_id, "received", json.dumps(command, separators=(",",":"), sort_keys=True), received, utc_now_iso()),
                    )
                return True
            except sqlite3.IntegrityError:
                return False

    def get(self, command_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self.conn.execute("SELECT * FROM command_ledger WHERE command_id=?", (command_id,)).fetchone()
        return dict(row) if row else None

    def set_state(self, command_id: str, state: str) -> None:
        with self._lock, self.conn:
            self.conn.execute("UPDATE command_ledger SET state=?,updated_at_utc=? WHERE command_id=?", (state, utc_now_iso(), command_id))

    def store_result(self, command_id: str, result: dict[str, Any]) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                "UPDATE command_ledger SET state='s9_pending',result_json=?,updated_at_utc=? WHERE command_id=?",
                (json.dumps(result, separators=(",",":"), sort_keys=True, default=str), utc_now_iso(), command_id),
            )

    def mark_s9(self, command_id: str, status: str, message_id: str, sequence: int) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                "UPDATE command_ledger SET state=?,s9_message_id=?,s9_sequence=?,updated_at_utc=? WHERE command_id=?",
                (status, message_id, int(sequence), utc_now_iso(), command_id),
            )

    def pending_results(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self.conn.execute("SELECT * FROM command_ledger WHERE state='s9_pending'").fetchall()]

    def uncertain(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self.conn.execute("SELECT * FROM command_ledger WHERE state IN ('received','executing')").fetchall()]

    def counts(self) -> dict[str, int]:
        with self._lock:
            rows = self.conn.execute("SELECT state,COUNT(*) n FROM command_ledger GROUP BY state").fetchall()
        return {str(r['state']): int(r['n']) for r in rows}

    def close(self) -> None:
        with self._lock: self.conn.close()


def _valid_uuid(value: str) -> bool:
    try:
        UUID(str(value)); return True
    except Exception:
        return False


def _parse_time(value: Any) -> datetime | None:
    if not value: return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


class CommandDownlinkProcessor:
    """D1 -> local authenticated PairController API -> durable S9 result."""
    def __init__(self, *, config: CentralSyncConfig, outbox: OutboxStore, backend_client: Any | None = None, local_api: Any | None = None, ledger: Any | None = None) -> None:
        self.config = config
        self.command_config = config.command_downlink
        self.outbox = outbox
        self.backend = backend_client or CentralBackendClient(config.backend, config.identity.gateway_id)
        self.local_api = local_api or LocalGatewayApiClient(config.local_gateway_api)
        self.ledger = ledger or CommandLedger(self.command_config.ledger_path)
        self._owns_backend = backend_client is None
        self._owns_local = local_api is None
        self._owns_ledger = ledger is None
        self.running = False
        self._stop = asyncio.Event()
        self.counters = {"poll_count":0,"commands_received":0,"duplicates":0,"rejected":0,"completed":0,"failed":0,"s9_enqueued":0,"last_error":None,"last_poll_utc":None}
        self._recovered = False

    async def close(self) -> None:
        if self._owns_backend: await self.backend.close()
        if self._owns_local: await self.local_api.close()
        if self._owns_ledger: await asyncio.to_thread(self.ledger.close)

    async def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        if not self.command_config.enabled: return
        self.running = True
        await self.recover_once()
        try:
            while not self._stop.is_set():
                await self.poll_once()
                try: await asyncio.wait_for(self._stop.wait(), timeout=max(0.2,self.command_config.poll_interval_sec))
                except asyncio.TimeoutError: pass
        finally:
            self.running = False; self._write_status()

    async def recover_once(self) -> None:
        if self._recovered: return
        self._recovered = True
        for row in await asyncio.to_thread(self.ledger.pending_results):
            try:
                result=json.loads(row.get('result_json') or '{}')
                if result: await self._enqueue_s9(str(row['command_id']), result)
            except Exception: pass
        # Fail safe: never replay a command whose field-write state became uncertain across restart.
        for row in await asyncio.to_thread(self.ledger.uncertain):
            cmd=json.loads(row.get('command_json') or '{}')
            result=self._result_base(cmd, str(row.get('received_at_utc') or utc_now_iso()))
            result.update(gateway_validation_ok=False, validation_reason="interrupted by gateway restart; not re-executed",
                          execution_started_at_utc=None, execution_finished_at_utc=utc_now_iso(), write_ok=None,
                          readback_requested=bool(cmd.get('requires_readback',True)), readback_value=None, verified=None,
                          final_status="failed", failure_reason="execution state uncertain after restart",
                          gateway_error_code="COMMAND_RECOVERY_UNCERTAIN", duration_ms=None)
            await asyncio.to_thread(self.ledger.store_result, str(row['command_id']), result)
            await self._enqueue_s9(str(row['command_id']), result)

    async def poll_once(self) -> dict[str, Any]:
        self.counters['poll_count'] += 1; self.counters['last_poll_utc'] = utc_now_iso()
        response = await self.backend.get_json(self.command_config.poll_path, params={
            "gateway_id": self.config.identity.gateway_id,
            "site_id": self.config.identity.site_id,
            "limit": self.command_config.max_commands_per_poll,
        })
        if response.status_code == 204:
            self._write_status(); return {"received":0,"processed":0}
        if not response.ok:
            self.counters['last_error'] = response.exception or f"HTTP {response.status_code}: {response.text[:200]}"
            self._write_status(); return {"received":0,"processed":0,"error":self.counters['last_error']}
        commands=(response.body or {}).get('commands',[])
        if not isinstance(commands,list):
            self.counters['last_error']="D1 response commands must be array"; self._write_status(); return {"received":0,"processed":0,"error":self.counters['last_error']}
        processed=0
        for command in commands[:self.command_config.max_commands_per_poll]:
            if isinstance(command,dict): await self.process_command(command); processed += 1
        self._write_status(); return {"received":len(commands),"processed":processed}

    async def process_command(self, command: dict[str, Any], *, forbid_execution: bool = False) -> dict[str, Any]:
        received=utc_now_iso(); self.counters['commands_received'] += 1
        command_id=str(command.get('command_id') or '')
        if not _valid_uuid(command_id):
            self.counters['rejected'] += 1; return {"accepted":False,"error":"INVALID_COMMAND_ID"}
        if not await asyncio.to_thread(self.ledger.claim, command_id, command, received):
            self.counters['duplicates'] += 1
            existing=await asyncio.to_thread(self.ledger.get, command_id)
            if existing and existing.get('state')=='s9_pending' and existing.get('result_json'):
                await self._enqueue_s9(command_id, json.loads(existing['result_json']))
            return {"accepted":True,"duplicate":True}

        result=self._result_base(command,received)
        error=self._validate(command, forbid_execution=forbid_execution)
        if error:
            result.update(gateway_validation_ok=False, validation_reason=error, execution_started_at_utc=None,
                          execution_finished_at_utc=utc_now_iso(), write_ok=None, readback_value=None, verified=None,
                          final_status="rejected", failure_reason=error, gateway_error_code="COMMAND_VALIDATION_REJECTED", duration_ms=None)
            self.counters['rejected'] += 1
        else:
            result['gateway_validation_ok']=True; result['validation_reason']='accepted by gateway command policy'
            await asyncio.to_thread(self.ledger.set_state, command_id, 'executing')
            started=time.monotonic(); result['execution_started_at_utc']=utc_now_iso()
            try:
                response=await self._execute(command)
                ok = response.get('ok', True) is not False
                result['execution_finished_at_utc']=utc_now_iso(); result['write_ok']=bool(ok)
                if bool(command.get('requires_readback', True)):
                    readback=await self.local_api.control_status_compact()
                    result['readback_value']=readback
                    result['verified']=self._verify(command, readback, response)
                else:
                    result['readback_value']=None; result['verified']=None
                if ok:
                    result['final_status']='completed'; result['failure_reason']=None; result['gateway_error_code']=None
                    self.counters['completed'] += 1
                else:
                    result['final_status']='failed'; result['failure_reason']=str(response.get('error') or 'local gateway returned ok=false'); result['gateway_error_code']='LOCAL_API_REJECTED'
                    self.counters['failed'] += 1
            except Exception as exc:
                result.update(execution_finished_at_utc=utc_now_iso(), write_ok=False, readback_value=None, verified=False,
                              final_status='failed', failure_reason=f"{type(exc).__name__}: {exc}", gateway_error_code='LOCAL_API_ERROR')
                self.counters['failed'] += 1
            result['duration_ms']=round((time.monotonic()-started)*1000.0,3)

        await asyncio.to_thread(self.ledger.store_result, command_id, result)
        await self._enqueue_s9(command_id,result)
        self._write_status()
        return {"accepted":True,"duplicate":False,"final_status":result['final_status']}

    def _validate(self, command: dict[str, Any], *, forbid_execution: bool) -> str | None:
        if forbid_execution: return "execution forbidden by caller/test"
        if str(command.get('gateway_id') or '') != self.config.identity.gateway_id: return "gateway_id mismatch"
        if str(command.get('site_id') or '') != self.config.identity.site_id: return "site_id mismatch"
        ctype=str(command.get('command_type') or '')
        if ctype not in self.command_config.allowed_command_types: return f"unsupported command_type {ctype!r}"
        expires=_parse_time(command.get('expires_at_utc'))
        if expires and expires < datetime.now(timezone.utc): return "command expired"
        role=str(command.get('requested_role') or '')
        if role not in {'internal','internal_admin','admin','service'}: return "requested_role is not authorized for BESS control"
        args=command.get('arguments')
        if not isinstance(args,dict): return "arguments must be object"
        if ctype != 'safe_stop_all' and not str(args.get('pair_id') or ''): return "pair_id required"
        if ctype in {'pair_precheck','pair_automatic_start','pair_set_power'}:
            if args.get('direction') not in {'charge','discharge'}: return "direction must be charge|discharge"
            try:
                if float(args.get('power_kw')) < 0: return "power_kw must be non-negative"
            except Exception: return "power_kw required"
        return None

    async def _execute(self, command: dict[str, Any]) -> dict[str, Any]:
        ctype=str(command['command_type']); a=dict(command.get('arguments') or {}); pair=str(a.get('pair_id') or '')
        stage=self.command_config.stage_confirmation_phrase; auto=self.command_config.automatic_confirmation_phrase
        if ctype=='pair_precheck':
            return await self.local_api.post_json(f"/api/control-sequence/{pair}/precheck", {"direction":a['direction'],"power_kw":float(a['power_kw'])})
        if ctype=='pair_automatic_start':
            body={"direction":a['direction'],"power_kw":float(a['power_kw']),"confirmation":auto}
            if a.get('ramp_step_kw') is not None: body['ramp_step_kw']=float(a['ramp_step_kw'])
            if a.get('ramp_interval_seconds') is not None: body['ramp_interval_seconds']=float(a['ramp_interval_seconds'])
            return await self.local_api.post_json(f"/api/control-sequence/{pair}/automatic-start",body)
        if ctype=='pair_set_power':
            return await self.local_api.post_json(f"/api/control-sequence/{pair}/set-power", {"direction":a['direction'],"power_kw":float(a['power_kw']),"confirmation":stage})
        if ctype=='pair_zero_power':
            return await self.local_api.post_json(f"/api/control-sequence/{pair}/zero-power", {"confirmation":stage})
        if ctype=='pair_safe_stop':
            return await self.local_api.post_json(f"/api/control-sequence/{pair}/safe-stop", {"confirmation":stage,"open_bms":bool(a.get('open_bms',False))})
        if ctype=='pair_abort':
            return await self.local_api.post_json(f"/api/control-sequence/{pair}/abort", {"confirmation":stage,"open_bms":bool(a.get('open_bms',False))})
        if ctype=='safe_stop_all':
            return await self.local_api.post_json("/api/control-sequence/safe-stop-all", {"confirmation":stage,"open_bms":bool(a.get('open_bms',False))})
        raise ValueError(f"unsupported command {ctype}")

    def _verify(self, command: dict[str, Any], readback: dict[str, Any], response: dict[str, Any]) -> bool | None:
        ctype=str(command.get('command_type')); a=command.get('arguments') or {}; pair=str(a.get('pair_id') or '')
        if ctype=='safe_stop_all':
            pairs=readback.get('pairs') or readback.get('by_pair_id') or {}
            vals=pairs.values() if isinstance(pairs,dict) else pairs if isinstance(pairs,list) else []
            return all(abs(float((p or {}).get('commanded_power_kw') or 0.0)) < 1e-6 for p in vals if isinstance(p,dict))
        pairs=readback.get('pairs') or readback.get('by_pair_id') or {}
        p=pairs.get(pair) if isinstance(pairs,dict) else next((x for x in pairs if isinstance(x,dict) and x.get('pair_id')==pair),None) if isinstance(pairs,list) else None
        if not isinstance(p,dict): return None
        if ctype in {'pair_zero_power','pair_safe_stop','pair_abort'}: return abs(float(p.get('commanded_power_kw') or 0.0)) < 1e-6
        if ctype=='pair_set_power':
            target=float(a.get('power_kw') or 0.0); signed=-target if a.get('direction')=='charge' else target
            actual=p.get('commanded_power_kw'); return actual is not None and abs(float(actual)-signed) <= max(1.0,abs(signed)*0.05)
        if ctype=='pair_automatic_start': return str(p.get('run_status') or '') in {'queued','running','completed'}
        if ctype=='pair_precheck': return response.get('ok',True) is not False
        return None

    def _result_base(self, command: dict[str, Any], received: str) -> dict[str, Any]:
        args=command.get('arguments') if isinstance(command.get('arguments'),dict) else {}
        pair=args.get('pair_id')
        return {
            "command_id": str(command.get('command_id') or ''),
            "correlation_id": command.get('correlation_id') or command.get('command_id'),
            "gateway_id": self.config.identity.gateway_id,
            "site_id": self.config.identity.site_id,
            "requested_at_utc": command.get('issued_at_utc'),
            "received_at_utc": received,
            "requested_by": command.get('requested_by'),
            "requested_role": command.get('requested_role'),
            "command_type": command.get('command_type'),
            "source_id": pair,
            "asset_id": pair,
            "signal_name": None,
            "requested_value": args,
            "gateway_validation_ok": None,
            "validation_reason": None,
            "execution_started_at_utc": None,
            "execution_finished_at_utc": None,
            "write_ok": None,
            "readback_requested": bool(command.get('requires_readback',True)),
            "readback_value": None,
            "verified": None,
            "final_status": "accepted",
            "failure_reason": None,
            "gateway_error_code": None,
            "duration_ms": None,
            "note": command.get('note'),
        }

    async def _enqueue_s9(self, command_id: str, result: dict[str, Any]) -> None:
        inserted,msg=await asyncio.to_thread(
            emit_message, config=self.config, outbox=self.outbox,
            stream=self.command_config.result_stream, substream=self.command_config.result_substream,
            priority=self.command_config.result_priority, records=[result], created_at_utc=result.get('execution_finished_at_utc') or utc_now_iso(),
        )
        if inserted:
            await asyncio.to_thread(self.ledger.mark_s9, command_id, str(result.get('final_status') or 'completed'), msg.message_id, msg.sequence)
            self.counters['s9_enqueued'] += 1

    def _write_status(self) -> None:
        safe_write_json(self.command_config.status_file, {"running":self.running,"counters":self.counters,"ledger":self.ledger.counts()})

    def status(self) -> dict[str, Any]:
        return {"running":self.running,"counters":dict(self.counters),"ledger":self.ledger.counts()}
