from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.config import GatewayConfig


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return f"pbkdf2_sha256$200000${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


@dataclass(frozen=True)
class User:
    username: str
    role: str
    password_hash: str
    enabled: bool = True


class AuthService:
    def __init__(self, config: GatewayConfig) -> None:
        self.config = config
        secret = os.getenv(config.security.jwt_secret_env)
        if not secret:
            if not config.security.allow_dev_default_credentials and config.mode != "mock":
                raise RuntimeError(f"{config.security.jwt_secret_env} must be set")
            secret = "development-only-change-this-secret"
        self.secret = secret
        self.algorithm = config.security.jwt_algorithm
        internal_password = os.getenv("KINETICS_INTERNAL_PASSWORD", "Internal@123")
        customer_password = os.getenv("KINETICS_CUSTOMER_PASSWORD", "Customer@123")
        self.users = {
            "internal": User("internal", "internal", hash_password(internal_password)),
            "customer": User("customer", "customer", hash_password(customer_password)),
        }

    def authenticate(self, username: str, password: str) -> User | None:
        user = self.users.get(username)
        if not user or not user.enabled or not verify_password(password, user.password_hash):
            return None
        return user

    def issue_token(self, user: User) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user.username,
            "role": user.role,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=self.config.security.token_expiry_minutes)).timestamp()),
            "gateway_id": self.config.gateway_id,
        }
        return jwt.encode(payload, self.secret, algorithm=self.algorithm)

    def decode_token(self, token: str) -> dict[str, Any]:
        try:
            return jwt.decode(token, self.secret, algorithms=[self.algorithm])
        except jwt.PyJWTError as error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from error

    def current_user(self, token: str) -> User:
        payload = self.decode_token(token)
        user = self.users.get(str(payload.get("sub")))
        if not user or not user.enabled:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User unavailable")
        return user


def build_user_dependencies(auth_service: AuthService):
    def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
        return auth_service.current_user(token)

    def require_internal(user: User = Depends(get_current_user)) -> User:
        if user.role != "internal":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Internal operator role required")
        return user

    return get_current_user, require_internal
