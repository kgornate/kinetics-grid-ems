from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.security.auth import AuthService, User, build_user_dependencies
from app.services.gateway_service import GatewayService


class LoginRequest(BaseModel):
    username: str
    password: str


class ControlRequest(BaseModel):
    value: Any


class SequencePrecheckRequest(BaseModel):
    direction: Literal["charge", "discharge"]
    power_kw: float


class SequenceEnableRackRequest(SequencePrecheckRequest):
    confirmation: str


class SequenceWriteRequest(BaseModel):
    confirmation: str


class SequencePowerRequest(SequencePrecheckRequest):
    confirmation: str


class SequenceAutomaticStartRequest(SequencePowerRequest):
    ramp_step_kw: float | None = None
    ramp_interval_seconds: float | None = None


class SequenceNextStepRequest(SequencePowerRequest):
    pass


class SequenceStopRequest(BaseModel):
    confirmation: str
    open_bms: bool = False


def build_router(service: GatewayService, auth: AuthService) -> APIRouter:
    router = APIRouter()
    current_user, require_internal = build_user_dependencies(auth)

    @router.post("/api/auth/login")
    def login(request: LoginRequest) -> dict[str, Any]:
        user = auth.authenticate(request.username, request.password)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        return {
            "access_token": auth.issue_token(user),
            "token_type": "bearer",
            "role": user.role,
            "username": user.username,
        }

    @router.get("/api/auth/me")
    def me(user: User = Depends(current_user)) -> dict[str, Any]:
        return {"username": user.username, "role": user.role}

    @router.get("/api/health")
    def health() -> dict[str, Any]:
        return service.health()

    @router.get("/api/assets")
    def assets(user: User = Depends(current_user)) -> dict[str, Any]:
        items = service.assets()
        return {"assets": items, "count": len(items)}

    @router.get("/api/telemetry/snapshot")
    def telemetry_snapshot(
        refresh: bool = Query(False),
        include_slow: bool = Query(False),
        include_bulk: bool = Query(False),
        user: User = Depends(current_user),
    ) -> dict[str, Any]:
        return service.refresh(include_slow=include_slow, include_bulk=include_bulk) if refresh else service.snapshot()


    @router.get("/api/telemetry/compact")
    def telemetry_compact(user: User = Depends(current_user)) -> dict[str, Any]:
        return service.compact_snapshot()

    @router.get("/api/diagnostics/data-rate")
    def diagnostics_data_rate(user: User = Depends(current_user)) -> dict[str, Any]:
        return service.data_rate_analysis()

    @router.get("/api/diagnostics/polling")
    def diagnostics_polling(user: User = Depends(current_user)) -> dict[str, Any]:
        return {"polling": service.health().get("polling", {})}

    @router.get("/api/telemetry/key-signals")
    def key_signals(user: User = Depends(current_user)) -> dict[str, Any]:
        snapshot = service.snapshot()
        return {
            "gateway_id": snapshot.get("gateway_id"),
            "timestamp": snapshot.get("timestamp"),
            "bank": snapshot.get("bank"),
            "racks": snapshot.get("racks"),
            "environment": snapshot.get("environment"),
            "pcs": snapshot.get("pcs"),
            "pcs_devices": snapshot.get("pcs_devices", {}),
        }

    @router.get("/api/bms/bank")
    def bms_bank(include_slow: bool = Query(False), user: User = Depends(current_user)) -> dict[str, Any]:
        snapshot = service.refresh(include_slow=True) if include_slow else service.snapshot()
        return snapshot["bank"]

    @router.get("/api/bms/racks")
    def bms_racks(user: User = Depends(current_user)) -> dict[str, Any]:
        racks = service.snapshot()["racks"]
        return {"racks": racks, "count": len(racks)}

    @router.get("/api/bms/racks/{rack_id}")
    def bms_rack(rack_id: int, include_all: bool = Query(False), user: User = Depends(current_user)) -> dict[str, Any]:
        if include_all:
            try:
                return service.rack_details(rack_id)
            except KeyError as error:
                raise HTTPException(status_code=404, detail=str(error)) from error
        for rack in service.snapshot()["racks"]:
            if int(rack.get("rack_id")) == rack_id:
                return rack
        raise HTTPException(status_code=404, detail=f"Rack {rack_id} not found")

    @router.get("/api/bms/racks/{rack_id}/details")
    def bms_rack_details(rack_id: int, user: User = Depends(current_user)) -> dict[str, Any]:
        try:
            return service.rack_details(rack_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.get("/api/bms/environment")
    def bms_environment(user: User = Depends(current_user)) -> dict[str, Any]:
        return service.snapshot()["environment"]

    @router.get("/api/bms/environment/{asset_id}")
    def bms_environment_asset(asset_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        assets = service.snapshot()["environment"]
        if asset_id not in assets:
            raise HTTPException(status_code=404, detail=f"Environment asset {asset_id} not found")
        return assets[asset_id]

    @router.get("/api/pcs")
    def pcs(user: User = Depends(current_user)) -> dict[str, Any]:
        """Backward-compatible primary PCS endpoint (normally pcs_1)."""
        return service.snapshot()["pcs"]

    @router.get("/api/pcs/all")
    def all_pcs(user: User = Depends(current_user)) -> dict[str, Any]:
        devices = service.snapshot().get("pcs_devices", {})
        return {
            "pcs": list(devices.values()),
            "by_asset_id": devices,
            "count": len(devices),
            "transport": service.config.pcs.transport,
        }

    @router.get("/api/pcs/{asset_id}")
    def pcs_asset(asset_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        try:
            return service.pcs_details(asset_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.get("/api/alarms")
    def alarms(active_only: bool = Query(True), limit: int = Query(500), user: User = Depends(current_user)) -> dict[str, Any]:
        items = service.store.list_alarms(active_only=active_only, limit=limit)
        return {"alarms": items, "count": len(items), "active_only": active_only}

    @router.get("/api/alarms/history")
    def alarm_history(
        limit: int = Query(500, ge=1, le=5000),
        since: str | None = Query(None),
        user: User = Depends(current_user),
    ) -> dict[str, Any]:
        items = service.store.list_alarm_history(limit=limit, since=since)
        return {"history": items, "count": len(items)}

    @router.get("/api/events")
    def events(
        limit: int = Query(500, ge=1, le=5000),
        since: str | None = Query(None),
        event_type: str | None = Query(None),
        user: User = Depends(current_user),
    ) -> dict[str, Any]:
        items = service.store.list_events(limit=limit, since=since, event_type=event_type)
        return {"events": items, "count": len(items)}

    @router.get("/api/historian/assets")
    def historian_assets(user: User = Depends(current_user)) -> dict[str, Any]:
        items = service.store.list_asset_ids()
        return {"asset_ids": items, "count": len(items)}

    @router.get("/api/historian/{asset_id}")
    def historian(
        asset_id: str,
        limit: int = Query(500, ge=1, le=5000),
        since: str | None = Query(None),
        user: User = Depends(current_user),
    ) -> dict[str, Any]:
        items = service.store.query_telemetry(asset_id, limit=limit, since=since)
        return {"asset_id": asset_id, "samples": items, "count": len(items)}

    @router.get("/api/commands/audit")
    def command_audit(limit: int = Query(200, ge=1, le=5000), user: User = Depends(require_internal)) -> dict[str, Any]:
        items = service.store.list_command_audit(limit)
        return {"commands": items, "count": len(items)}


    @router.get("/api/control-sequence/capabilities")
    def control_sequence_capabilities(user: User = Depends(current_user)) -> dict[str, Any]:
        return service.control_sequence.capabilities()

    @router.get("/api/control-sequence/{pair_id}/status")
    def control_sequence_status(
        pair_id: str,
        fresh: bool = Query(True),
        user: User = Depends(current_user),
    ) -> dict[str, Any]:
        try:
            return service.control_sequence.status(pair_id, fresh=fresh)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @router.post("/api/control-sequence/{pair_id}/automatic-start", status_code=202)
    def control_sequence_automatic_start(
        pair_id: str,
        request: SequenceAutomaticStartRequest,
        user: User = Depends(require_internal),
    ) -> dict[str, Any]:
        try:
            return service.control_sequence.automatic_start(
                user.username,
                pair_id,
                request.direction,
                request.power_kw,
                request.confirmation,
                ramp_step_kw=request.ramp_step_kw,
                ramp_interval_seconds=request.ramp_interval_seconds,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except (ValueError, RuntimeError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @router.post("/api/control-sequence/{pair_id}/next-step")
    def control_sequence_next_step(
        pair_id: str,
        request: SequenceNextStepRequest,
        user: User = Depends(require_internal),
    ) -> dict[str, Any]:
        try:
            return service.control_sequence.next_step(
                user.username,
                pair_id,
                request.direction,
                request.power_kw,
                request.confirmation,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @router.post("/api/control-sequence/{pair_id}/precheck")
    def control_sequence_precheck(
        pair_id: str,
        request: SequencePrecheckRequest,
        user: User = Depends(require_internal),
    ) -> dict[str, Any]:
        try:
            return service.control_sequence.precheck(pair_id, request.direction, request.power_kw)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @router.post("/api/control-sequence/{pair_id}/enable-rack")
    def control_sequence_enable_rack(
        pair_id: str,
        request: SequenceEnableRackRequest,
        user: User = Depends(require_internal),
    ) -> dict[str, Any]:
        try:
            return service.control_sequence.enable_rack(
                user.username, pair_id, request.direction, request.power_kw, request.confirmation
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @router.post("/api/control-sequence/{pair_id}/start-insulation")
    def control_sequence_start_insulation(
        pair_id: str,
        request: SequenceWriteRequest,
        user: User = Depends(require_internal),
    ) -> dict[str, Any]:
        try:
            return service.control_sequence.start_insulation(
                user.username, pair_id, request.confirmation
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @router.get("/api/control-sequence/{pair_id}/verify-insulation")
    def control_sequence_verify_insulation(
        pair_id: str,
        user: User = Depends(require_internal),
    ) -> dict[str, Any]:
        try:
            return service.control_sequence.verify_insulation(pair_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @router.post("/api/control-sequence/{pair_id}/start-precharge")
    def control_sequence_start_precharge(
        pair_id: str,
        request: SequenceWriteRequest,
        user: User = Depends(require_internal),
    ) -> dict[str, Any]:
        try:
            return service.control_sequence.start_precharge(
                user.username, pair_id, request.confirmation
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @router.post("/api/control-sequence/{pair_id}/recover-bms")
    def control_sequence_recover_bms(
        pair_id: str,
        request: SequenceWriteRequest,
        user: User = Depends(require_internal),
    ) -> dict[str, Any]:
        try:
            return service.control_sequence.recover_bms(
                user.username, pair_id, request.confirmation
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @router.get("/api/control-sequence/{pair_id}/verify-ready")
    def control_sequence_verify_ready(
        pair_id: str,
        user: User = Depends(require_internal),
    ) -> dict[str, Any]:
        try:
            return service.control_sequence.verify_ready(pair_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @router.post("/api/control-sequence/{pair_id}/prepare-pcs-standby")
    def control_sequence_prepare_pcs_standby(
        pair_id: str,
        request: SequenceWriteRequest,
        user: User = Depends(require_internal),
    ) -> dict[str, Any]:
        try:
            return service.control_sequence.prepare_pcs_standby(
                user.username, pair_id, request.confirmation
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @router.post("/api/control-sequence/{pair_id}/configure-pcs")
    def control_sequence_configure_pcs(
        pair_id: str,
        request: SequenceWriteRequest,
        user: User = Depends(require_internal),
    ) -> dict[str, Any]:
        try:
            return service.control_sequence.configure_pcs(
                user.username, pair_id, request.confirmation
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @router.post("/api/control-sequence/{pair_id}/start-pcs")
    def control_sequence_start_pcs(
        pair_id: str,
        request: SequenceWriteRequest,
        user: User = Depends(require_internal),
    ) -> dict[str, Any]:
        try:
            return service.control_sequence.start_pcs(
                user.username, pair_id, request.confirmation
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @router.post("/api/control-sequence/{pair_id}/set-power")
    def control_sequence_set_power(
        pair_id: str,
        request: SequencePowerRequest,
        user: User = Depends(require_internal),
    ) -> dict[str, Any]:
        try:
            return service.control_sequence.set_power(
                user.username, pair_id, request.direction, request.power_kw, request.confirmation
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @router.post("/api/control-sequence/{pair_id}/zero-power")
    def control_sequence_zero_power(
        pair_id: str,
        request: SequenceWriteRequest,
        user: User = Depends(require_internal),
    ) -> dict[str, Any]:
        try:
            return service.control_sequence.zero_power(
                user.username, pair_id, request.confirmation
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @router.get("/api/control-sequence/{pair_id}/verify-power")
    def control_sequence_verify_power(
        pair_id: str,
        user: User = Depends(require_internal),
    ) -> dict[str, Any]:
        try:
            return service.control_sequence.verify_power(pair_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @router.post("/api/control-sequence/{pair_id}/safe-stop")
    def control_sequence_safe_stop(
        pair_id: str,
        request: SequenceStopRequest,
        user: User = Depends(require_internal),
    ) -> dict[str, Any]:
        try:
            return service.control_sequence.safe_stop(
                user.username, pair_id, request.confirmation, open_bms=request.open_bms
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @router.post("/api/control-sequence/{pair_id}/abort")
    def control_sequence_abort(
        pair_id: str,
        request: SequenceStopRequest,
        user: User = Depends(require_internal),
    ) -> dict[str, Any]:
        try:
            return service.control_sequence.abort(
                user.username,
                pair_id,
                request.confirmation,
                open_bms=request.open_bms,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @router.get("/api/control/capabilities")
    def control_capabilities(user: User = Depends(current_user)) -> dict[str, Any]:
        bms = service.bms_catalog.select(writable=True, include_reserved=False)
        pcs = [p for p in service.pcs_catalog.points if "W" in str(p.get("access", "R")).upper()]
        return {
            "bms_write_enabled": service.config.bms.write_enabled,
            "pcs_write_enabled": service.config.pcs.write_enabled,
            "bms_points": bms,
            "pcs_points": pcs,
            "counts": {"bms": len(bms), "pcs": len(pcs)},
        }

    @router.get("/api/protocols/bms")
    def bms_protocol_catalog(
        scope: str | None = Query(None),
        category: str | None = Query(None),
        writable: bool | None = Query(None),
        user: User = Depends(current_user),
    ) -> dict[str, Any]:
        points = service.bms_catalog.select(scope=scope, category=category, writable=writable, include_reserved=False)
        return {"summary": service.bms_catalog.summary(), "points": points, "count": len(points)}

    @router.get("/api/protocols/pcs")
    def pcs_protocol_catalog(user: User = Depends(current_user)) -> dict[str, Any]:
        return {"summary": service.pcs_catalog.summary(), "points": list(service.pcs_catalog.points)}

    @router.post("/api/control/{asset_id}/{point_key}")
    def control(
        asset_id: str,
        point_key: str,
        request: ControlRequest,
        user: User = Depends(require_internal),
    ) -> dict[str, Any]:
        try:
            return service.execute_control(user.username, asset_id, point_key, request.value)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @router.get("/api/mock/scenarios")
    def mock_scenarios(user: User = Depends(current_user)) -> dict[str, Any]:
        return {"scenarios": service.scenarios, "current": service.config.mock.scenario}

    @router.post("/api/mock/scenario/{scenario}")
    def set_mock_scenario(scenario: str, user: User = Depends(require_internal)) -> dict[str, Any]:
        if service.config.mode not in {"mock", "mixed"}:
            raise HTTPException(status_code=409, detail="Mock scenarios are disabled in this mode")
        try:
            return service.set_mock_scenario(scenario)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @router.get("/api/storage/status")
    def storage_status(user: User = Depends(current_user)) -> dict[str, Any]:
        return service.store.status()

    @router.post("/api/storage/retention/run")
    def run_retention(user: User = Depends(require_internal)) -> dict[str, Any]:
        return {"removed": service.store.enforce_retention(), "storage": service.store.status()}

    @router.get("/api/logs")
    def logs(lines: int = Query(300, ge=1, le=5000), user: User = Depends(require_internal)) -> dict[str, Any]:
        entries = service.store.read_log_tail(lines=lines)
        return {"lines": entries, "count": len(entries), "path": str(service.store.log_path)}

    @router.get("/api/export/historian/{asset_id}.csv", response_class=PlainTextResponse)
    def export_historian(
        asset_id: str,
        limit: int = Query(5000, ge=1, le=5000),
        since: str | None = Query(None),
        user: User = Depends(current_user),
    ) -> PlainTextResponse:
        rows = service.store.query_telemetry(asset_id, limit=limit, since=since)
        return PlainTextResponse(service.store.to_csv(rows), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{asset_id}.csv"'})

    @router.get("/api/export/alarms.csv", response_class=PlainTextResponse)
    def export_alarms(limit: int = Query(5000, ge=1, le=5000), user: User = Depends(current_user)) -> PlainTextResponse:
        rows = service.store.list_alarm_history(limit=limit)
        return PlainTextResponse(service.store.to_csv(rows), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="alarms.csv"'})

    @router.get("/api/export/commands.csv", response_class=PlainTextResponse)
    def export_commands(limit: int = Query(5000, ge=1, le=5000), user: User = Depends(require_internal)) -> PlainTextResponse:
        rows = service.store.list_command_audit(limit=limit)
        return PlainTextResponse(service.store.to_csv(rows), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="commands.csv"'})

    @router.websocket("/ws/telemetry")
    async def telemetry_socket(
        websocket: WebSocket,
        token: str = Query(...),
        mode: str = Query("delta"),
    ) -> None:
        try:
            auth.current_user(token)
        except HTTPException:
            await websocket.close(code=4401)
            return
        await websocket.accept()
        try:
            if mode == "full":
                while True:
                    await websocket.send_json(service.snapshot())
                    await asyncio.sleep(service.config.telemetry_interval_seconds)
            last_sequence = int(service.snapshot().get("sequence") or 0)
            await websocket.send_json(service.compact_snapshot())
            while True:
                updates = service.updates_since(last_sequence)
                for update in updates:
                    await websocket.send_json(update)
                    last_sequence = max(last_sequence, int(update.get("sequence") or last_sequence))
                await asyncio.sleep(0.2)
        except WebSocketDisconnect:
            return

    @router.websocket("/ws/alarms")
    async def alarm_socket(websocket: WebSocket, token: str = Query(...)) -> None:
        try:
            auth.current_user(token)
        except HTTPException:
            await websocket.close(code=4401)
            return
        await websocket.accept()
        try:
            while True:
                alarms = service.store.list_alarms(active_only=True, limit=1000)
                await websocket.send_json({"alarms": alarms, "count": len(alarms)})
                await asyncio.sleep(max(1.0, service.config.telemetry_interval_seconds))
        except WebSocketDisconnect:
            return

    return router
