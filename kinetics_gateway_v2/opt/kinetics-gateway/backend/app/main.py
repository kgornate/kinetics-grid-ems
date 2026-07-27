from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Awaitable, Callable

from fastapi import FastAPI, Request

from app.api.routes import build_router
from app.core.config import load_config
from app.security.auth import AuthService
from app.services.gateway_service import GatewayService
from app.services.logging_setup import configure_logging
from app.storage.sqlite_store import SQLiteStore


config = load_config(os.getenv("KINETICS_CONFIG"))
store = SQLiteStore(config.storage)
configure_logging(store.log_path)
logger = logging.getLogger("kinetics.http")
auth = AuthService(config)
service = GatewayService(config, store)


async def periodic_loop(name: str, interval: float, action: Callable[[], object]) -> None:
    """Run an independent polling class without allowing drift to accumulate."""
    next_run = time.monotonic() + max(interval, 0.1)
    while True:
        await asyncio.sleep(max(0.0, next_run - time.monotonic()))
        started = time.monotonic()
        try:
            await asyncio.to_thread(action)
        except Exception:
            logger.exception("Background task failed: %s", name)
        next_run += max(interval, 0.1)
        if next_run < time.monotonic():
            next_run = time.monotonic() + max(interval, 0.1)


async def maintenance_loop() -> None:
    while True:
        await asyncio.sleep(3600)
        removed = await asyncio.to_thread(store.enforce_retention)
        if any(removed.values()):
            logger.info("Retention removed records: %s", removed)


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = []
    if config.bms.enabled:
        tasks.extend(
            [
                asyncio.create_task(
                    periodic_loop("bms-fast", config.bms.poll_fast_seconds, lambda: service.poll_bms_class("fast")),
                    name="kinetics-bms-fast",
                ),
                asyncio.create_task(
                    periodic_loop("bms-normal", config.bms.poll_normal_seconds, lambda: service.poll_bms_class("normal")),
                    name="kinetics-bms-normal",
                ),
                asyncio.create_task(
                    periodic_loop("bms-slow", config.bms.poll_slow_seconds, lambda: service.poll_bms_class("slow")),
                    name="kinetics-bms-slow",
                ),
                asyncio.create_task(
                    periodic_loop("bms-bulk", config.bms.poll_bulk_seconds, lambda: service.poll_bms_class("bulk")),
                    name="kinetics-bms-bulk",
                ),
            ]
        )
    if config.pcs.enabled:
        tasks.append(
            asyncio.create_task(
                periodic_loop("pcs", config.pcs.poll_seconds, service.poll_pcs),
                name="kinetics-pcs",
            )
        )
    tasks.append(asyncio.create_task(maintenance_loop(), name="kinetics-maintenance"))
    store.event(
        "gateway",
        "Gateway application started",
        payload={
            "mode": config.mode,
            "gateway_id": config.gateway_id,
            "scheduler": {
                "bms_fast_seconds": config.bms.poll_fast_seconds,
                "bms_normal_seconds": config.bms.poll_normal_seconds,
                "bms_slow_seconds": config.bms.poll_slow_seconds,
                "bms_bulk_seconds": config.bms.poll_bulk_seconds,
                "pcs_seconds": config.pcs.poll_seconds,
            },
        },
    )
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        store.event("gateway", "Gateway application stopped")


app = FastAPI(
    title="Kinetics Gateway V2",
    version="2.2.0-pcs-rtu-4pcs",
    description=(
        "FRDM i.MX93 BMS/PCS gateway with unchanged BMS Modbus TCP support, four-PCS Modbus RTU/RS485, "
        "delta WebSockets, JWT security, compressed SQLite historian and mock/hardware modes"
    ),
    lifespan=lifespan,
)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("HTTP request failed method=%s path=%s", request.method, request.url.path)
        raise
    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info("%s %s status=%s elapsed_ms=%.1f", request.method, request.url.path, response.status_code, elapsed_ms)
    return response


app.include_router(build_router(service, auth))
