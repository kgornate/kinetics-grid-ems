from __future__ import annotations

from typing import Any

import httpx

from .config import LocalGatewayApiConfig


class LocalGatewayApiError(RuntimeError):
    pass


class LocalGatewayApiClient:
    """Small authenticated loopback API client for read-only producer inputs."""

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
        token = await self._ensure_token()
        response = await self.client.get(
            self.config.health_url,
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code == 401:
            # Cached token may have expired. One forced re-login is enough; the
            # producer loop handles later failures without affecting the uploader.
            self._token = None
            token = await self._ensure_token(force_login=True)
            response = await self.client.get(
                self.config.health_url,
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code != 200:
            raise LocalGatewayApiError(
                f"GET {self.config.health_path} returned HTTP {response.status_code}: {response.text[:500]}"
            )
        try:
            body = response.json()
        except Exception as exc:
            raise LocalGatewayApiError(f"gateway health response is not valid JSON: {exc}") from exc
        if not isinstance(body, dict):
            raise LocalGatewayApiError("gateway health response must be a JSON object")
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
