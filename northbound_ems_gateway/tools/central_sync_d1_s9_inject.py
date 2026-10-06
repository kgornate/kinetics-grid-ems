#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from nb_ems_gateway.central_sync.command_downlink import CommandDownlinkProcessor
from nb_ems_gateway.central_sync.config import load_central_sync_config
from nb_ems_gateway.central_sync.outbox import OutboxStore


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Safe D1 -> S9 commissioning injector")
    p.add_argument("--config", default="configs/central_sync.json")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--file", help="D1 command JSON file")
    g.add_argument("--expired-safe-test", action="store_true", help="Generate an expired source_standby D1 command; no field write can occur")
    p.add_argument("--source-id", default="external_ems_1")
    p.add_argument("--allow-execution", action="store_true", help="Allow a valid command to reach local control API (default: forbidden)")
    return p.parse_args()


def expired_command(config, source_id: str) -> dict:
    now = datetime.now(timezone.utc)
    issued = now - timedelta(minutes=2)
    expires = now - timedelta(minutes=1)
    return {
        "command_id": str(uuid4()),
        "gateway_id": config.identity.gateway_id,
        "site_id": config.identity.site_id,
        "issued_at_utc": issued.isoformat().replace("+00:00", "Z"),
        "expires_at_utc": expires.isoformat().replace("+00:00", "Z"),
        "requested_by": "g10_commissioning_test",
        "requested_role": "internal_admin",
        "command_type": "source_standby",
        "arguments": {"source_id": source_id},
        "requires_readback": True,
        "priority": "critical",
        "note": "G10 D1/S9 expired-command commissioning test; must not execute field write",
    }


async def amain() -> int:
    args = parse_args()
    config = load_central_sync_config(args.config)
    outbox = OutboxStore(
        config.outbox.path,
        max_db_size_mb=config.outbox.max_db_size_mb,
        min_free_space_mb=config.outbox.min_free_space_mb,
        required_mount_path=config.outbox.required_mount_path,
        fail_if_mount_missing=config.outbox.fail_if_mount_missing,
    )
    processor = CommandDownlinkProcessor(config=config, outbox=outbox)
    try:
        if args.expired_safe_test:
            command = expired_command(config, args.source_id)
        else:
            command = json.loads(Path(args.file).read_text(encoding="utf-8"))
            if not isinstance(command, dict):
                raise SystemExit("D1 file must contain one JSON object")
        before = outbox.current_sequence(config.command_downlink.s9_stream, config.command_downlink.s9_substream)
        print("D1_COMMAND_ID=", command.get("command_id"))
        print("D1_COMMAND_TYPE=", command.get("command_type"))
        print("D1_EXECUTION_ALLOWED=", bool(args.allow_execution))
        print("S9_SEQUENCE_BEFORE=", before)
        result = await processor.process_command(command, forbid_execution=not args.allow_execution)
        after = outbox.current_sequence(config.command_downlink.s9_stream, config.command_downlink.s9_substream)
        print("PROCESS_RESULT=", json.dumps(result, sort_keys=True))
        print("S9_SEQUENCE_AFTER=", after)
        print("D1_S9_INJECTION=PASS" if after >= before else "D1_S9_INJECTION=FAIL")
        return 0
    finally:
        await processor.close()
        outbox.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain()))
