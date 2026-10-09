from __future__ import annotations

from typing import Any

import httpx

from .config import LocalGatewayApiConfig


class LocalGatewayApiError(RuntimeError):
    pass


class LocalGatewayApiClient:
    """Authenticated loopback client used by Central Sync.

    The client talks only to the already-running gateway REST API. It never
    performs Modbus I/O itself, which keeps Central Sync isolated from the
    southbound polling/control implementation.
    """

    def __init__(self, config: LocalGatewayApiConfig, client: httpx.AsyncClient | Any | None = None) -> None:
        self.config = config
        self._token: str | None = config.resolved_token()
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            verify=config.verify_tls,
            timeout=httpx.Timeout(config.timeout_sec, connect=config.connect_timeout_sec),
            headers={"User-Agent": config.user_agent},
        )

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def health(self) -> dict[str, Any]:
        return await self.get_json(self.config.health_path)

    async def telemetry_snapshot(self) -> dict[str, Any]:
        return await self.get_json(self.config.telemetry_snapshot_path)

    async def normalized_snapshot(self) -> dict[str, Any]:
        return await self.get_json(self.config.normalized_snapshot_path)

    async def alarms_history(self, **params: Any) -> Any:
        return await self.get_json_any(self.config.alarms_history_path, params=params)

    async def commands_audit(self, **params: Any) -> Any:
        return await self.get_json_any(self.config.commands_audit_path, params=params)

    async def control_status_all(self) -> dict[str, Any]:
        return await self.get_json(self.config.control_status_all_path)

    async def control_status_compact(self) -> dict[str, Any]:
        return await self.get_json(self.config.control_status_compact_path)

    async def platform_readiness(self) -> dict[str, Any]:
        return await self.get_json(self.config.platform_readiness_path)

    async def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        body = await self.get_json_any(path, params=params)
        if not isinstance(body, dict):
            raise LocalGatewayApiError(f"gateway API {path} response must be a JSON object")
        return body

    async def get_json_any(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        token = await self._ensure_token()
        url = self.config.base_url.rstrip("/") + (path if path.startswith("/") else f"/{path}")
        response = await self.client.get(url, params=params, headers={"Authorization": f"Bearer {token}"})
        if response.status_code == 401:
            self._token = None
            token = await self._ensure_token(force_login=True)
            response = await self.client.get(url, params=params, headers={"Authorization": f"Bearer {token}"})
        if response.status_code != 200:
            raise LocalGatewayApiError(f"GET {path} returned HTTP {response.status_code}: {response.text[:500]}")
        try:
            return response.json()
        except Exception as exc:
            raise LocalGatewayApiError(f"gateway API {path} response is not valid JSON: {exc}") from exc

    async def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        token = await self._ensure_token()
        url = self.config.base_url.rstrip("/") + (path if path.startswith("/") else f"/{path}")
        response = await self.client.post(url, json=payload, headers={"Authorization": f"Bearer {token}"})
        if response.status_code == 401:
            self._token = None
            token = await self._ensure_token(force_login=True)
            response = await self.client.post(url, json=payload, headers={"Authorization": f"Bearer {token}"})
        if not (200 <= response.status_code < 300):
            raise LocalGatewayApiError(f"POST {path} returned HTTP {response.status_code}: {response.text[:500]}")
        try:
            body = response.json()
        except Exception as exc:
            raise LocalGatewayApiError(f"gateway API {path} response is not valid JSON: {exc}") from exc
        if not isinstance(body, dict):
            raise LocalGatewayApiError(f"gateway API {path} response must be a JSON object")
        return body

    async def _ensure_token(self, *, force_login: bool = False) -> str:
        if self._token and not force_login:
            return self._token
        static_token = self.config.resolved_token()
        if static_token and not force_login:
            self._token = static_token
            return self._token
        password = self.config.resolved_password()
        if not password:
            raise LocalGatewayApiError(
                "local gateway API credentials not configured: set "
                f"{self.config.password_env} or {self.config.token_env}"
            )
        response = await self.client.post(
            self.config.login_url,
            json={"username": self.config.username, "password": password},
        )
        if response.status_code != 200:
            raise LocalGatewayApiError(
                f"local gateway login failed HTTP {response.status_code}: {response.text[:500]}"
            )
        body = response.json()
        token = str(body.get("access_token") or "").strip()
        if not token:
            raise LocalGatewayApiError("local gateway login response did not contain access_token")
        self._token = token
        return token
