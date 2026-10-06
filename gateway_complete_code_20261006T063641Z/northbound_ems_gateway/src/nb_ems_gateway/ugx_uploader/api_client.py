from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import GatewayAPIConfig

LOG = logging.getLogger(__name__)


class LocalGatewayAPIClient:
    def __init__(self, config: GatewayAPIConfig) -> None:
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self._token: str | None = config.resolved_access_token()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    def login(self) -> None:
        if self._token:
            return
        password = self.config.resolved_password()
        if not password:
            raise RuntimeError(
                "local gateway API password is missing. Set gateway_api.password or export the configured password_env."
            )
        url = f"{self.base_url}/api/auth/login"
        with httpx.Client(timeout=self.config.timeout_sec) as client:
            resp = client.post(url, json={"username": self.config.username, "password": password})
        if resp.status_code >= 300:
            raise RuntimeError(f"local gateway login failed: HTTP {resp.status_code} {resp.text[:300]}")
        data = resp.json()
        self._token = data.get("access_token")
        if not self._token:
            raise RuntimeError("local gateway login response did not include access_token")

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.login()
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.config.timeout_sec) as client:
            resp = client.get(url, params=params or {}, headers=self._headers())
        if resp.status_code == 401:
            self._token = None
            self.login()
            with httpx.Client(timeout=self.config.timeout_sec) as client:
                resp = client.get(url, params=params or {}, headers=self._headers())
        if resp.status_code >= 300:
            raise RuntimeError(f"local gateway GET {path} failed: HTTP {resp.status_code} {resp.text[:300]}")
        return resp.json()
