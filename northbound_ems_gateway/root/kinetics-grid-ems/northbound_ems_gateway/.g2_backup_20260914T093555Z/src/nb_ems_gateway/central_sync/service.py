from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
from pathlib import Path

from .config import load_central_sync_config
from .outbox import OutboxStore
from .uploader import CentralSyncUploader


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ornate Central EMS Central Sync service")
    parser.add_argument("--config", default="configs/central_sync.json")
    parser.add_argument("--once", action="store_true", help="Run at most one transport attempt then exit")
    parser.add_argument("--status", action="store_true", help="Print current outbox/service status then exit")
    return parser.parse_args()


async def amain() -> int:
    args = parse_args()
    config = load_central_sync_config(args.config)
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    outbox = OutboxStore(
        config.outbox.path,
        max_db_size_mb=config.outbox.max_db_size_mb,
        min_free_space_mb=config.outbox.min_free_space_mb,
        required_mount_path=config.outbox.required_mount_path,
        fail_if_mount_missing=config.outbox.fail_if_mount_missing,
    )
    uploader = CentralSyncUploader(config=config, outbox=outbox)

    try:
        if args.status:
            print(json.dumps(uploader.status(), indent=2))
            return 0
        if not config.enabled:
            print(f"Central Sync disabled by config: {args.config}")
            return 0
        if args.once:
            await uploader.run_once()
            print(json.dumps(uploader.status(), indent=2))
            return 0

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(uploader.stop()))
            except NotImplementedError:
                pass
        await uploader.run_forever()
        return 0
    finally:
        await uploader.close()
        outbox.close()


def main() -> None:
    raise SystemExit(asyncio.run(amain()))


if __name__ == "__main__":
    main()
