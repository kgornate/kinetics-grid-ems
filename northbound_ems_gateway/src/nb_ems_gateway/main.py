from __future__ import annotations
import argparse
import asyncio
import logging

import uvicorn

from nb_ems_gateway.api.server import create_app
from nb_ems_gateway.app.dependency_container import DependencyContainer
from nb_ems_gateway.config.loader import load_config
from nb_ems_gateway.control.control_service import ControlService
from nb_ems_gateway.control.soc_protection import SOCProtectionController
from nb_ems_gateway.dictionary.register_map import RegisterMap
from nb_ems_gateway.polling.scheduler import PollingScheduler
from nb_ems_gateway.protocol.reader import build_readers
from nb_ems_gateway.server_upload.uploader import ServerUploadService

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s - %(message)s')

VERSION = '0.9.0-soc-protection'

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
        await container.soc_protection_controller.start()
        app = create_app(container)
        main_server = uvicorn.Server(uvicorn.Config(app, host=config.api.host, port=config.api.port, log_level='info'))
        if config.logs_api.enabled and config.logs_api.port != config.api.port:
            logs_app = create_app(container)
            logs_server = uvicorn.Server(uvicorn.Config(logs_app, host=config.logs_api.host, port=config.logs_api.port, log_level='info'))
            await asyncio.gather(main_server.serve(), logs_server.serve())
        else:
            await main_server.serve()
    finally:
        await uploader.stop()
        if container.soc_protection_controller:
            await container.soc_protection_controller.stop()
        await scheduler.stop()
        container.close()

def main() -> None:
    asyncio.run(amain())

if __name__ == '__main__':
    main()
