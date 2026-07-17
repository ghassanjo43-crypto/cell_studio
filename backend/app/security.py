"""Password hashing and JWT access tokens.

Password hashing uses stdlib PBKDF2-HMAC-SHA256 (no native build dependencies —
portable and defensible). Tokens are signed JWTs (PyJWT, HS256).
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from .config import get_settings

_PBKDF2_ITERATIONS = 240_000
_ALGORITHM_TAG = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    """Return a self-describing password hash: ``pbkdf2_sha256$iters$salt$hash``."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"{_ALGORITHM_TAG}${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Verify ``password`` against an encoded hash, in constant time."""
    try:
        tag, iterations_s, salt_hex, hash_hex = encoded.split("$")
    except ValueError:
        return False
    if tag != _ALGORITHM_TAG:
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations_s)
    )
    return hmac.compare_digest(digest.hex(), hash_hex)


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    """Create a signed JWT whose ``sub`` claim is ``subject`` (the user id)."""
    settings = get_settings()
    minutes = expires_minutes if expires_minutes is not None else settings.access_token_expire_minutes
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT, returning its claims. Raises on invalid/expired."""
    settings = get_settings()
    result: dict[str, Any] = jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    return result
