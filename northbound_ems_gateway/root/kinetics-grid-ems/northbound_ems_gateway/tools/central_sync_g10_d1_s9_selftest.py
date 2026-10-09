#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from nb_ems_gateway.central_sync.client import TransportResponse
from nb_ems_gateway.central_sync.command_downlink import CommandDownlinkProcessor, CommandLedger
from nb_ems_gateway.central_sync.config import CentralSyncConfig
from nb_ems_gateway.central_sync.outbox import OutboxStore


class FakeLocalApi:
    def __init__(self):
        self.calls=[]
    async def post_json(self, path, body):
        self.calls.append((path, body))
        return {"ok": True, "path": path, "body": body, "readback": {"safe": True}}
    async def close(self):
        pass


class FakeBackend:
    def __init__(self, commands=None):
        self.commands=list(commands or [])
        self.calls=[]
    async def get_json(self, path, *, params=None):
        self.calls.append((path, params))
        commands=self.commands
        self.commands=[]
        return TransportResponse(status_code=200, body={"commands": commands}, text="")
    async def close(self):
        pass


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def command(cfg, *, expired=False, ctype="source_standby", role="internal_admin", args=None):
    now=datetime.now(timezone.utc)
    if expired:
        issued=now-timedelta(minutes=2)
        expires=now-timedelta(minutes=1)
    else:
        issued=now-timedelta(seconds=1)
        expires=now+timedelta(minutes=2)
    return {
        "command_id": str(uuid4()),
        "gateway_id": cfg.identity.gateway_id,
        "site_id": cfg.identity.site_id,
        "issued_at_utc": iso(issued),
        "expires_at_utc": iso(expires),
        "requested_by": "selftest",
        "requested_role": role,
        "command_type": ctype,
        "arguments": args if args is not None else {"source_id":"external_ems_1"},
        "requires_readback": True,
        "priority": "critical",
        "note": "g10 selftest",
    }


def read_s9(dbpath):
    con=sqlite3.connect(dbpath)
    try:
        rows=con.execute("SELECT sequence,payload_json FROM outbox_messages WHERE stream='command_results' ORDER BY sequence").fetchall()
        out=[]
        for seq,payload in rows:
            out.append((seq,json.loads(payload)))
        return out
    finally:
        con.close()


async def main():
    raw=json.loads(Path("configs/central_sync.json").read_text())
    with tempfile.TemporaryDirectory(prefix="g10_d1_s9_") as td:
        raw["outbox"]["path"]=str(Path(td)/"outbox.db")
        raw["outbox"]["required_mount_path"]=None
        raw["outbox"]["fail_if_mount_missing"]=False
        raw["outbox"]["max_db_size_mb"]=64
        raw["outbox"]["min_free_space_mb"]=1
        raw["command_downlink"]["ledger_path"]=str(Path(td)/"ledger.db")
        raw["command_downlink"]["status_file"]=str(Path(td)/"status.json")
        cfg=CentralSyncConfig.model_validate(raw)
        assert cfg.command_downlink.enabled is False
        assert cfg.uploader.worker_count == 1
        assert cfg.backlog_replay.enabled is False
        assert all([
            cfg.fast_bess.enabled,cfg.general_assets.enabled,cfg.gateway_health.enabled,
            cfg.alarms_events.enabled,cfg.soc_controller.enabled,cfg.solis.enabled,
            cfg.edge_ai.enabled,cfg.configuration_audit.enabled,
        ])
        print("PASS: G10 config preserves S1-S8, one uploader worker and replay OFF")

        outbox=OutboxStore(cfg.outbox.path,max_db_size_mb=64,min_free_space_mb=1,required_mount_path=None,fail_if_mount_missing=False)
        local=FakeLocalApi()
        backend=FakeBackend()
        ledger=CommandLedger(cfg.command_downlink.ledger_path)
        p=CommandDownlinkProcessor(config=cfg,outbox=outbox,backend_client=backend,local_api=local,ledger=ledger)
        try:
            c1=command(cfg,expired=True)
            r=await p.process_command(c1)
            assert r["validation_code"]=="COMMAND_EXPIRED"
            assert local.calls==[]
            rows=read_s9(cfg.outbox.path)
            assert len(rows)==1 and rows[0][0]==1
            rec=rows[0][1]["records"][0]
            assert rec["final_status"]=="rejected" and rec["gateway_error_code"]=="COMMAND_EXPIRED"
            print("PASS: expired D1 is rejected and emits S9 without any local control call")

            r2=await p.process_command(c1)
            assert r2["duplicate"] is True
            assert outbox.current_sequence("command_results","gateway")==1
            assert local.calls==[]
            print("PASS: duplicate command_id is idempotent and never re-executes")

            c2=command(cfg,expired=False)
            r=await p.process_command(c2,forbid_execution=True)
            assert r["validation_code"]=="TEST_EXECUTION_DISABLED"
            assert local.calls==[]
            print("PASS: commissioning injector defaults to execution-forbidden")

            c3=command(cfg,expired=False)
            r=await p.process_command(c3,forbid_execution=False)
            assert r["final_status"]=="completed"
            assert len(local.calls)==1
            assert local.calls[0][0]=="/api/control/sources/external_ems_1/standby"
            rows=read_s9(cfg.outbox.path)
            rec=rows[-1][1]["records"][0]
            assert rec["gateway_validation_ok"] is True and rec["final_status"]=="completed"
            print("PASS: valid D1 routes through authenticated local API abstraction and emits completed S9")

            c4=command(cfg,role="customer_admin")
            r=await p.process_command(c4)
            assert r["validation_code"]=="ROLE_NOT_ALLOWED"
            assert len(local.calls)==1
            print("PASS: D1 rejects non-internal_admin role before execution")

            c5=command(cfg,ctype="solis_on_off",args={"target":"OFF"})
            r=await p.process_command(c5)
            assert r["validation_code"]=="COMMAND_TYPE_NOT_ALLOWED"
            assert len(local.calls)==1
            print("PASS: solis_on_off remains blocked pending separate safety review")

            c6=command(cfg,expired=True)
            backend.commands=[c6]
            result=await p.poll_once()
            assert result["processed"]==1
            assert backend.calls and backend.calls[-1][0]==cfg.command_downlink.poll_path
            assert len(local.calls)==1
            print("PASS: backend poll envelope commands[] feeds the same safe D1 processor")

            statuses={r[0] for r in sqlite3.connect(cfg.command_downlink.ledger_path).execute("SELECT state FROM command_ledger").fetchall()}
            assert "rejected" in statuses and "completed" in statuses
            print("PASS: persistent command ledger records terminal lifecycle states")

            print("G10_D1_S9_SELFTEST=PASS")
        finally:
            await p.close()
            # p does not own injected ledger/local/backend, close explicit ledger.
            ledger.close()
            outbox.close()


if __name__=="__main__":
    raise SystemExit(asyncio.run(main()))
