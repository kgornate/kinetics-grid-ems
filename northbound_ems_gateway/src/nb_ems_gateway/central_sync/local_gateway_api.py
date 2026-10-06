from __future__ import annotations

from typing import Any

import httpx

from .config import LocalGatewayApiConfig


class LocalGatewayApiError(RuntimeError):
    pass


class LocalGatewayApiClient:
    """Small authenticated loopback API client for read-only producer inputs.

    Central Sync never polls field Modbus through this client.  It consumes the
    already-running gateway/controller API on loopback and reuses one authenticated
    HTTP client/token across S3/S5/S6 producer reads.
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
        return await self._get_json(self.config.health_path)

    async def controller_status(self) -> dict[str, Any]:
        return await self._get_json(self.config.controller_status_path)

    async def controller_history(self, **params: Any) -> dict[str, Any]:
        return await self._get_json(self.config.controller_history_path, params=params)

    async def solis_status(self) -> dict[str, Any]:
        return await self._get_json(self.config.solis_status_path)

    async def solis_history(self, **params: Any) -> dict[str, Any]:
        return await self._get_json(self.config.solis_history_path, params=params)

    async def post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """Execute an existing authenticated local Gateway API command.

        D1 never writes Modbus directly; all execution passes through the same
        internal_admin-protected API/control service already used by operators.
        """
        token = await self._ensure_token()
        url = self.config.base_url.rstrip("/") + (path if path.startswith("/") else f"/{path}")
        response = await self.client.post(
            url,
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code == 401:
            self._token = None
            token = await self._ensure_token(force_login=True)
            response = await self.client.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise LocalGatewayApiError(
                f"POST {path} returned HTTP {response.status_code}: {response.text[:500]}"
            )
        try:
            data = response.json()
        except Exception as exc:
            raise LocalGatewayApiError(f"gateway API {path} response is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise LocalGatewayApiError(f"gateway API {path} response must be a JSON object")
        return data

    async def _get_json(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        token = await self._ensure_token()
        url = self.config.base_url.rstrip("/") + (path if path.startswith("/") else f"/{path}")
        response = await self.client.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code == 401:
            # Cached token may have expired. One forced re-login is enough; each
            # producer loop handles later failures without affecting the uploader.
            self._token = None
            token = await self._ensure_token(force_login=True)
            response = await self.client.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code != 200:
            raise LocalGatewayApiError(
                f"GET {path} returned HTTP {response.status_code}: {response.text[:500]}"
            )
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
        try:
            body = response.json()
            token = str(body.get("access_token") or "").strip()
        except Exception as exc:
            raise LocalGatewayApiError(f"local gateway login response is invalid: {exc}") from exc
        if not token:
            raise LocalGatewayApiError("local gateway login response did not contain access_token")
        self._token = token
        return token
