from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import uvicorn

from nb_ems_gateway.api.server import create_app
from nb_ems_gateway.app.dependency_container import DependencyContainer
from nb_ems_gateway.app.lifecycle import install_logging
from nb_ems_gateway.app.runtime import build_reader
from nb_ems_gateway.cli.args import parse_args
from nb_ems_gateway.cli.diagnostics import print_startup_banner
from nb_ems_gateway.config.loader import load_config
from nb_ems_gateway.dictionary.map_loader import load_register_map
from nb_ems_gateway.polling.polling_service import PollingService
from nb_ems_gateway.polling.scheduler import PollingScheduler, intervals_from_config
from nb_ems_gateway.protocol.read_plan import create_read_plans


def main() -> None:
    install_logging()
    args = parse_args()
    config = load_config(args.config)
    register_map_path = Path(config.register_map.path)
    if not register_map_path.is_absolute():
        register_map_path = Path.cwd() / register_map_path
    register_map = load_register_map(register_map_path)
    print_startup_banner(config, register_map, args.mock)

    container = DependencyContainer.create(config=config, register_map=register_map)
    reader = build_reader(config, register_map, mock=args.mock)
    plans = create_read_plans(register_map, max_registers_per_read=config.polling.max_registers_per_read)
    polling_service = PollingService(reader=reader, plans=plans, decoding_config=config.decoding, polling_config=config.polling)

    if args.no_api:
        for group in sorted(plans):
            container.apply_poll_result(polling_service.poll_once(group))
        print(container.health_engine.snapshot())
        return

    app = create_app(container)

    async def run() -> None:
        scheduler = PollingScheduler(
            polling_service=polling_service,
            on_result=container.apply_poll_result,
            intervals=intervals_from_config(config),
        )
        await scheduler.start()
        server_config = uvicorn.Config(app, host=config.api.host, port=config.api.port, log_level="info")
        server = uvicorn.Server(server_config)
        try:
            await server.serve()
        finally:
            await scheduler.stop()
            reader.close()
            container.close()

    asyncio.run(run())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
