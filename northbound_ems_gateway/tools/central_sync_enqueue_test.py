#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from nb_ems_gateway.central_sync.config import load_central_sync_config
from nb_ems_gateway.central_sync.contracts import make_message
from nb_ems_gateway.central_sync.outbox import OutboxStore


def main() -> None:
    p = argparse.ArgumentParser(description="Enqueue synthetic G1 transport test messages")
    p.add_argument("--config", default="configs/central_sync.json")
    p.add_argument("--count", type=int, default=3)
    p.add_argument("--stream", default="gateway_health")
    p.add_argument("--substream", default="g1_transport_test")
    p.add_argument("--priority", default="P2", choices=["P0","P1","P2","P3","P4"])
    args = p.parse_args()

    cfg = load_central_sync_config(args.config)
    store = OutboxStore(
        cfg.outbox.path,
        max_db_size_mb=cfg.outbox.max_db_size_mb,
        min_free_space_mb=cfg.outbox.min_free_space_mb,
        required_mount_path=cfg.outbox.required_mount_path,
        fail_if_mount_missing=cfg.outbox.fail_if_mount_missing,
    )
    created = []
    try:
        for n in range(max(1, args.count)):
            seq = store.next_sequence(args.stream, args.substream)
            msg = make_message(
                schema_version=cfg.identity.schema_version,
                gateway_id=cfg.identity.gateway_id,
                site_id=cfg.identity.site_id,
                stream=args.stream,
                substream=args.substream,
                sequence=seq,
                priority=args.priority,
                records=[{
                    "kind": "g1_transport_test",
                    "ordinal": n + 1,
                    "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                }],
            )
            inserted = store.enqueue(msg)
            created.append({"message_id": msg.message_id, "sequence": seq, "inserted": inserted})
        print(json.dumps({"created": created, "outbox": store.stats()}, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()
