from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request, status
from pydantic import BaseModel

from nb_ems_gateway.config.models import AuthConfig, AuthUserConfig

_TOKEN_PREFIX = "nbems_pbkdf2_sha256"


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_sec: int
    username: str
    role: str
    display_name: str


class CurrentUser(BaseModel):
    username: str
    role: str
    display_name: str

    @property
    def is_internal_admin(self) -> bool:
        return self.role == "internal_admin"

    @property
    def is_customer_admin(self) -> bool:
        return self.role == "customer_admin"


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    user: CurrentUser | None = None
    reason: str | None = None


def make_password_hash(password: str, *, iterations: int = 210000) -> str:
    salt = secrets.token_urlsafe(18)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return f"{_TOKEN_PREFIX}${iterations}${salt}${base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        prefix, iterations_s, salt, digest_b64 = stored_hash.split("$", 3)
        if prefix != _TOKEN_PREFIX:
            return False
        iterations = int(iterations_s)
        expected = _b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def authenticate_user(auth_config: AuthConfig, username: str, password: str) -> AuthResult:
    if not auth_config.enabled:
        return AuthResult(False, reason="authentication disabled")
    for configured_user in auth_config.users:
        if configured_user.username != username:
            continue
        if not configured_user.enabled:
            return AuthResult(False, reason="user disabled")
        password_hash = _resolve_password_hash(configured_user)
        if not password_hash:
            return AuthResult(False, reason="password hash not configured")
        if not verify_password(password, password_hash):
            return AuthResult(False, reason="invalid password")
        return AuthResult(
            True,
            user=CurrentUser(
                username=configured_user.username,
                role=configured_user.role,
                display_name=configured_user.display_name or configured_user.username,
            ),
        )
    return AuthResult(False, reason="unknown user")


def create_access_token(auth_config: AuthConfig, user: CurrentUser) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=auth_config.token_expiry_minutes)
    payload = {
        "sub": user.username,
        "role": user.role,
        "display_name": user.display_name,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": "northbound-ems-gateway",
    }
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = f"{_json_b64(header)}.{_json_b64(payload)}"
    signature = hmac.new(_jwt_secret(auth_config), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64encode(signature)}"


def verify_access_token(auth_config: AuthConfig, token: str) -> CurrentUser:
    if not auth_config.enabled:
        return CurrentUser(username="auth_disabled", role="internal_admin", display_name="Auth Disabled")
    try:
        header_b64, payload_b64, signature_b64 = token.split(".", 2)
        signing_input = f"{header_b64}.{payload_b64}"
        expected = hmac.new(_jwt_secret(auth_config), signing_input.encode("ascii"), hashlib.sha256).digest()
        supplied = _b64decode(signature_b64)
        if not hmac.compare_digest(expected, supplied):
            raise ValueError("bad signature")
        payload = json.loads(_b64decode(payload_b64).decode("utf-8"))
        exp = int(payload.get("exp", 0))
        if datetime.now(timezone.utc).timestamp() >= exp:
            raise ValueError("token expired")
        username = str(payload.get("sub") or "")
        role = str(payload.get("role") or "")
        display_name = str(payload.get("display_name") or username)
        if not username or role not in auth_config.allowed_roles:
            raise ValueError("invalid token payload")
        if not _user_exists_and_enabled(auth_config, username, role):
            raise ValueError("user no longer enabled")
        return CurrentUser(username=username, role=role, display_name=display_name)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid or expired token: {exc}") from exc


def extract_token_from_request(request: Request) -> str | None:
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    # Used only for WebSocket and CSV/manual-browser cases where custom headers are inconvenient.
    token = request.query_params.get("token") or request.query_params.get("access_token")
    return token.strip() if token else None


async def require_auth(request: Request) -> CurrentUser:
    token = extract_token_from_request(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer token")
    return verify_access_token(request.app.state.container.config.auth, token)


def require_roles(*roles: str):
    async def _dependency(request: Request) -> CurrentUser:
        user = await require_auth(request)
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role not allowed for this API")
        return user
    return _dependency


def audit_auth_event(request: Request, event_type: str, message: str, payload: dict[str, Any] | None = None, *, user: CurrentUser | None = None, severity: str = "info") -> None:
    try:
        c = request.app.state.container
        p = dict(payload or {})
        p["client"] = request.client.host if request.client else None
        p["path"] = request.url.path
        if user:
            p["username"] = user.username
            p["role"] = user.role
        c.event_logger.log(severity, event_type, message, p, source="auth", asset_id=None)
    except Exception:
        pass


def _resolve_password_hash(user: AuthUserConfig) -> str | None:
    if user.password_hash:
        return user.password_hash
    if user.password_hash_env:
        return os.getenv(user.password_hash_env)
    return None


def _user_exists_and_enabled(auth_config: AuthConfig, username: str, role: str) -> bool:
    for u in auth_config.users:
        if u.username == username and u.role == role and u.enabled:
            return True
    return False


def _jwt_secret(auth_config: AuthConfig) -> bytes:
    secret = os.getenv(auth_config.jwt_secret_env) if auth_config.jwt_secret_env else None
    secret = secret or auth_config.jwt_secret
    if not secret:
        # Stable development fallback. Production configs should override this.
        secret = "northbound-dev-change-this-jwt-secret"
    return secret.encode("utf-8")


def _json_b64(value: dict[str, Any]) -> str:
    return _b64encode(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))
