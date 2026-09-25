from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal

from .config import load_central_sync_config
from .gateway_health_producer import GatewayHealthProducer
from .fast_bess_producer import FastBESSProducer
from .general_asset_producer import GeneralAssetProducer
from .outbox import OutboxStore
from .uploader import CentralSyncUploader


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ornate Central EMS Central Sync service")
    parser.add_argument("--config", default="configs/central_sync.json")
    parser.add_argument("--once", action="store_true", help="Run at most one transport attempt then exit")
    parser.add_argument("--status", action="store_true", help="Print current outbox/service status then exit")
    parser.add_argument(
        "--produce-once",
        choices=["gateway_health", "fast_bess", "general_assets"],
        help="Run one producer collection/enqueue cycle then exit without uploading",
    )
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
    health_producer = GatewayHealthProducer(config=config, outbox=outbox)
    fast_bess_producer = FastBESSProducer(config=config, outbox=outbox)
    general_asset_producer = GeneralAssetProducer(config=config, outbox=outbox)

    async def stop_all() -> None:
        await general_asset_producer.stop()
        await fast_bess_producer.stop()
        await health_producer.stop()
        await uploader.stop()

    try:
        if args.status:
            print(
                json.dumps(
                    {
                        "central_sync": uploader.status(),
                        "gateway_health_producer": health_producer.status(),
                        "fast_bess_producer": fast_bess_producer.status(),
                        "general_asset_producer": general_asset_producer.status(),
                    },
                    indent=2,
                )
            )
            return 0

        if not config.enabled:
            print(f"Central Sync disabled by config: {args.config}")
            return 0

        if args.produce_once == "gateway_health":
            if not config.gateway_health.enabled:
                print("gateway_health producer disabled by config")
                return 2
            result = await health_producer.collect_once(force_heartbeat=True, reason="manual_test")
            print(json.dumps(result, indent=2))
            return 0

        if args.produce_once == "fast_bess":
            if not config.fast_bess.enabled:
                print("fast_bess producer disabled by config")
                return 2
            result = await fast_bess_producer.collect_once()
            print(json.dumps(result, indent=2))
            return 0


        if args.produce_once == "general_assets":
            if not config.general_assets.enabled:
                print("general_assets producer disabled by config")
                return 2
            result = await general_asset_producer.collect_once()
            print(json.dumps(result, indent=2))
            return 0

        if args.once:
            await uploader.run_once()
            print(json.dumps(uploader.status(), indent=2))
            return 0

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(stop_all()))
            except NotImplementedError:
                pass

        tasks = [asyncio.create_task(uploader.run_forever(), name="central-sync-uploader")]
        if config.gateway_health.enabled:
            tasks.append(
                asyncio.create_task(
                    health_producer.run_forever(),
                    name="gateway-health-producer",
                )
            )

        if config.fast_bess.enabled:
            tasks.append(
                asyncio.create_task(
                    fast_bess_producer.run_forever(),
                    name="fast-bess-producer",
                )
            )


        if config.general_assets.enabled:
            tasks.append(
                asyncio.create_task(
                    general_asset_producer.run_forever(),
                    name="general-asset-producer",
                )
            )

        # If any top-level loop exits unexpectedly, stop the others and let
        # systemd restart the process. Producer-internal poll failures are caught
        # by the producer and do not terminate the service.
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            exc = task.exception()
            if exc:
                raise exc
        await stop_all()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        return 0
    finally:
        await general_asset_producer.close()
        await fast_bess_producer.close()
        await health_producer.close()
        await uploader.close()
        outbox.close()


def main() -> None:
    raise SystemExit(asyncio.run(amain()))


if __name__ == "__main__":
    main()
