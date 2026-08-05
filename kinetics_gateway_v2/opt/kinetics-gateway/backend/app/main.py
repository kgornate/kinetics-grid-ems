from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import build_router
from app.core.config import load_config
from app.security.auth import AuthService
from app.services.gateway_service import GatewayService
from app.services.http_admission import HttpAdmissionController, is_priority_http_path
from app.services.logging_setup import configure_logging
from app.services.runtime_metrics import RuntimeMetrics
from app.storage.sqlite_store import SQLiteStore


config = load_config(os.getenv("KINETICS_CONFIG"))
store = SQLiteStore(config.storage)
configure_logging(store.log_path)
logger = logging.getLogger("kinetics.http")
auth = AuthService(config)
runtime_metrics = RuntimeMetrics()
http_admission = HttpAdmissionController(
    max_concurrent=config.http_max_concurrent_requests,
    reserved_priority=config.http_reserved_priority_requests,
    wait_timeout_seconds=config.http_admission_timeout_seconds,
)
service = GatewayService(
    config,
    store,
    runtime_metrics=runtime_metrics,
    eager_initialization=False,
)


async def periodic_loop(name: str, interval: float, action: Callable[[], object]) -> None:
    """Run an independent polling class without allowing drift to accumulate."""
    next_run = time.monotonic() + max(interval, 0.1)
    while True:
        await asyncio.sleep(max(0.0, next_run - time.monotonic()))
        started = time.monotonic()
        failed = False
        try:
            await asyncio.to_thread(action)
        except Exception:
            failed = True
            logger.exception("Background task failed: %s", name)
        elapsed_ms = (time.monotonic() - started) * 1000
        next_run += max(interval, 0.1)
        missed = 0
        if next_run < time.monotonic():
            missed = 1
            next_run = time.monotonic() + max(interval, 0.1)
        runtime_metrics.background_finished(name, elapsed_ms, error=failed, missed=missed)


async def event_loop_monitor(interval: float = 1.0) -> None:
    next_run = time.monotonic() + interval
    while True:
        await asyncio.sleep(max(0.0, next_run - time.monotonic()))
        now = time.monotonic()
        runtime_metrics.event_loop_sample(
            max(0.0, (now - next_run) * 1000),
            len(asyncio.all_tasks()),
        )
        next_run = now + interval


async def maintenance_loop() -> None:
    while True:
        await asyncio.sleep(3600)
        removed = await asyncio.to_thread(store.enforce_retention)
        await asyncio.to_thread(service._storage_status, force=True)
        if any(removed.values()):
            logger.info("Retention removed records: %s", removed)


async def data_rate_cache_loop() -> None:
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(service.refresh_data_rate_analysis)
        except Exception:
            logger.exception("Data-rate cache refresh failed")


async def polling_supervisor() -> None:
    """Warm hardware caches without delaying API startup, then start pollers."""
    children: list[asyncio.Task] = []
    try:
        await asyncio.to_thread(service.initialize)
        if config.bms.enabled:
            children.extend(
                asyncio.create_task(
                    periodic_loop(name, interval, lambda poll=name: service.poll_bms_class(poll)),
                    name=f"kinetics-bms-{name}",
                )
                for name, interval in (
                    ("fast", config.bms.poll_fast_seconds),
                    ("normal", config.bms.poll_normal_seconds),
                    ("slow", config.bms.poll_slow_seconds),
                    ("bulk", config.bms.poll_bulk_seconds),
                )
            )
        if config.pcs.enabled:
            children.append(asyncio.create_task(
                periodic_loop("pcs", config.pcs.poll_seconds, service.poll_pcs),
                name="kinetics-pcs",
            ))
        children.append(asyncio.create_task(data_rate_cache_loop(), name="kinetics-data-rate-cache"))
        await asyncio.gather(*children)
    finally:
        for child in children:
            child.cancel()
        for child in children:
            with contextlib.suppress(asyncio.CancelledError):
                await child


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [asyncio.create_task(polling_supervisor(), name="kinetics-polling-supervisor")]
    tasks.append(asyncio.create_task(maintenance_loop(), name="kinetics-maintenance"))
    tasks.append(asyncio.create_task(event_loop_monitor(), name="kinetics-runtime-metrics"))
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
    version="2.6.0-multi-pair-control",
    description=(
        "FRDM i.MX93 BMS/PCS gateway with unchanged BMS Modbus TCP support, four-PCS Modbus RTU/RS485, "
        "independent multi-pair BMS-to-PCS control with contention-safe runtime monitoring, delta WebSockets, JWT security, compressed SQLite historian and mock/hardware modes"
    ),
    lifespan=lifespan,
)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    started = time.perf_counter()
    runtime_metrics.request_started()
    status_code = 500
    lease = None
    try:
        priority = is_priority_http_path(request.url.path)
        lease = await http_admission.acquire(priority=priority)
        if lease is None:
            runtime_metrics.http_admission_rejected(priority=priority)
            response = JSONResponse(
                status_code=503,
                content={
                    "detail": "Gateway HTTP capacity is busy; retry shortly",
                    "retryable": True,
                },
                headers={"Retry-After": "1"},
            )
        else:
            runtime_metrics.http_admission_accepted(priority=priority)
            response = await call_next(request)
        status_code = response.status_code
    except Exception:
        logger.exception("HTTP request failed method=%s path=%s", request.method, request.url.path)
        raise
    finally:
        if lease is not None:
            http_admission.release(lease)
            runtime_metrics.http_admission_released(priority=lease.priority)
        elapsed_ms = (time.perf_counter() - started) * 1000
        runtime_metrics.request_finished(request.method, request.url.path, status_code, elapsed_ms)
    if elapsed_ms >= runtime_metrics.slow_request_ms:
        logger.warning("Slow HTTP request method=%s path=%s status=%s elapsed_ms=%.1f", request.method, request.url.path, response.status_code, elapsed_ms)
    else:
        logger.info("%s %s status=%s elapsed_ms=%.1f", request.method, request.url.path, response.status_code, elapsed_ms)
    return response


app.include_router(build_router(service, auth, runtime_metrics))
