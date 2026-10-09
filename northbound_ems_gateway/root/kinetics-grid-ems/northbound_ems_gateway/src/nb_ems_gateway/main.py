from __future__ import annotations
import argparse
import asyncio
import logging

import uvicorn
from nb_ems_gateway.api.public_http_maintenance import install_public_http_maintenance

from nb_ems_gateway.api.server import create_app
from nb_ems_gateway.app.dependency_container import DependencyContainer
from nb_ems_gateway.config.loader import load_config
from nb_ems_gateway.control.control_service import ControlService
from nb_ems_gateway.control.soc_protection import SOCProtectionController
from nb_ems_gateway.dictionary.register_map import RegisterMap
from nb_ems_gateway.polling.scheduler import PollingScheduler
from nb_ems_gateway.protocol.reader import build_readers
from nb_ems_gateway.server_upload.uploader import ServerUploadService
from nb_ems_gateway.storage.fast_bess_logger import FastBESSLogger
from nb_ems_gateway.assets.general_asset_live_publisher import GeneralAssetLivePublisher

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s - %(message)s')

VERSION = '0.10.0-operator-control'

def parse_args():
    p = argparse.ArgumentParser(description='NorthBound EMS Gateway')
    p.add_argument('--config', default='configs/development.json')
    p.add_argument('--mock', action='store_true')
    p.add_argument('--no-api', action='store_true')
    return p.parse_args()

async def amain() -> None:
    args = parse_args()
    config = load_config(args.config)
    reg = RegisterMap.load(config.register_map.path)
    container = DependencyContainer.create(config=config, register_map=reg)
    readers = build_readers(config, args.mock)
    container.readers = readers
    container.control_service = ControlService(container, readers)
    container.soc_protection_controller = SOCProtectionController(container)
    container.fast_bess_logger = FastBESSLogger(config.fast_bess_logger, container)
    container.general_asset_live_publisher = GeneralAssetLivePublisher(config.general_asset_live_publisher, container)
    scheduler = PollingScheduler(container, readers)
    uploader = ServerUploadService(config.server_upload, container)
    container.server_upload_service = uploader

    print('NorthBound EMS Gateway')
    print(f'  version: {VERSION}')
    print(f'  mode: {config.gateway.mode}')
    print(f'  mock: {args.mock}')
    print(f'  sources: {len(container.sources)}')
    for s in container.sources:
        print(f'    - {s.source_id}: {s.host}:{s.port}, unit={s.unit_id}, iface={s.interface}')
    print(f'  register map: {config.register_map.path}')
    print(f'  register points per source: {reg.point_count}')
    print(f'  runtime points total: {reg.point_count * len(container.sources)}')
    print(f'  writable points per source: {len(reg.writable_points)}')
    print(f'  API: http://{config.api.host}:{config.api.port}')
    print(f'  logs API: enabled={config.logs_api.enabled}, http://{config.logs_api.host}:{config.logs_api.port}')
    print(f'  storage: {config.storage.path}')
    print(f'  storage required mount: {config.storage.required_mount_path}')
    print(f'  telemetry historian: enabled={config.storage.telemetry_history_enabled}, mode={config.storage.store_mode}, interval={config.storage.snapshot_interval_sec}s')
    print(f'  fast BESS logger: enabled={config.fast_bess_logger.enabled}, interval={config.fast_bess_logger.interval_sec}s, profile={config.fast_bess_logger.profile_name}')
    print(f'  general asset live publisher: enabled={config.general_asset_live_publisher.enabled}, interval={config.general_asset_live_publisher.interval_sec}s, path={config.general_asset_live_publisher.live_snapshot_path}')
    print(f'  server upload: enabled={config.server_upload.enabled}, interface={config.server_upload.network_interface}')
    print(f'  auth: enabled={config.auth.enabled}, users={len(config.auth.users)}')
    print(f'  commands: enabled={config.api.commands_enabled}')
    print(f'  control: enabled={config.control.enabled}')
    print(f'  soc protection: enabled={config.soc_protection.enabled}, dry_run={config.soc_protection.dry_run}, interval={config.soc_protection.interval_sec}s')
    try:
        await scheduler.start()
        if args.no_api:
            await scheduler.poll_once()
            await scheduler.stop()
            return
        await uploader.start()
        if container.fast_bess_logger:
            await container.fast_bess_logger.start()
        if container.general_asset_live_publisher:
            await container.general_asset_live_publisher.start()
        await container.soc_protection_controller.start()
        app = create_app(container)
        # Public HTTP maintenance gate.
        # Localhost APIs remain available.
        # Public Cloudflare HTTP is blocked only when
        # /etc/nb_ems_block_public_http exists.
        install_public_http_maintenance(app)

        main_server = uvicorn.Server(uvicorn.Config(app, host=config.api.host, port=config.api.port, log_level='info'))

        if config.logs_api.enabled and config.logs_api.port != config.api.port:
            logs_app = create_app(container)
            install_public_http_maintenance(logs_app)
            logs_server = uvicorn.Server(uvicorn.Config(logs_app, host=config.logs_api.host, port=config.logs_api.port, log_level='info'))
            await asyncio.gather(main_server.serve(), logs_server.serve())
        else:
            await main_server.serve()
    finally:
        await uploader.stop()
        if container.soc_protection_controller:
            await container.soc_protection_controller.stop()
        if container.general_asset_live_publisher:
            await container.general_asset_live_publisher.stop()
        if container.fast_bess_logger:
            await container.fast_bess_logger.stop()
        await scheduler.stop()
        container.close()

def main() -> None:
    asyncio.run(amain())

if __name__ == '__main__':
    main()
