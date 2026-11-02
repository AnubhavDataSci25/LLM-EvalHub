"""Authentication, cryptographic operations, and credential security.

Provides:
- Password hashing (bcrypt) with constant-time verification
- Password strength validation
- JWT access tokens (short-lived)
- Refresh token hashing & rotation
- Fernet encryption for workspace provider API keys at rest
- In-memory rate limiting with sliding window
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from cryptography.fernet import Fernet

from app.core.config import settings
from app.core.exceptions import AuthenticationError

# --- Password Hashing & Verification -----------------------------------------


DUMMY_BCRYPT_HASH = "$2b$12$ynKDkL9.9GcxccJ1hQUzVem4dn0ESflqtCIyqRDdKXEDiRI1zb7tK"


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt with salt rounds."""
    # bcrypt limits passwords to 72 bytes
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a stored bcrypt hash in constant time."""
    try:
        pwd_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except Exception:
        # Fallback dummy comparison to prevent timing discrepancies
        try:
            bcrypt.checkpw(b"dummy_password_timing_pad", DUMMY_BCRYPT_HASH.encode("utf-8"))
        except Exception:
            pass
        return False


def validate_password_strength(password: str) -> tuple[bool, str | None]:
    """Validate password against complexity and length rules."""
    if len(password) < settings.password_min_length:
        return False, f"Password must be at least {settings.password_min_length} characters long."
    if not any(c.isalpha() for c in password):
        return False, "Password must contain at least one letter."
    if not any(c.isdigit() or not c.isalnum() for c in password):
        return False, "Password must contain at least one digit or special character."
    return True, None


# --- JWT Access Tokens -------------------------------------------------------


def create_access_token(
    user_id: str,
    email: str,
    workspace_id: str | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Issue a signed, short-lived JWT access token."""
    now = datetime.now(UTC)
    expires = now + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "type": "access",
    }
    if workspace_id:
        payload["wid"] = workspace_id
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Validate signature and decode an access token. Raises AuthenticationError on failure."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "type"]},
        )
        if payload.get("type") != "access":
            raise AuthenticationError("Invalid token type.")
        return payload
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired.") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid authentication token.") from exc


# --- Refresh Tokens ----------------------------------------------------------


def generate_refresh_token() -> str:
    """Generate a high-entropy URL-safe random string for refresh tokens."""
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    """Hash a token using SHA-256 for safe storage at rest."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_compare(val1: str, val2: str) -> bool:
    """Compare two strings in constant time to prevent timing attacks."""
    return hmac.compare_digest(val1.encode("utf-8"), val2.encode("utf-8"))


# --- Fernet Encryption for Provider Keys -------------------------------------


def get_fernet_key() -> bytes:
    """Obtain or derive a 32-byte url-safe base64-encoded Fernet key."""
    if settings.encryption_key:
        candidate = settings.encryption_key.strip().encode("utf-8")
        try:
            Fernet(candidate)
            return candidate
        except Exception:
            pass
    # Derive deterministically from secret_key
    derived = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(derived)


def encrypt_secret(plain_text: str) -> str:
    """Encrypt sensitive secret text (e.g. workspace provider key) at rest."""
    if not plain_text:
        return ""
    fernet = Fernet(get_fernet_key())
    return fernet.encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_secret(cipher_text: str) -> str:
    """Decrypt sensitive secret text stored at rest."""
    if not cipher_text:
        return ""
    fernet = Fernet(get_fernet_key())
    return fernet.decrypt(cipher_text.encode("utf-8")).decode("utf-8")


def mask_secret(plain_text: str | None) -> str | None:
    """Return a masked representation (at most the last 4 characters). Never exposes the key."""
    if not plain_text:
        return None
    clean = plain_text.strip()
    if len(clean) <= 4:
        return "..." + clean
    return "..." + clean[-4:]


# --- Rate Limiting -----------------------------------------------------------


class InMemoryRateLimiter:
    """Thread-safe in-memory sliding window rate limiter."""

    def __init__(self, max_requests: int = 5, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._attempts: dict[str, list[float]] = {}

    def is_allowed(self, key: str) -> bool:
        """Check if request for key is within rate limit; records timestamp if allowed."""
        now = time.time()
        with self._lock:
            timestamps = self._attempts.get(key, [])
            cutoff = now - self.window_seconds
            valid = [t for t in timestamps if t > cutoff]
            if len(valid) >= self.max_requests:
                self._attempts[key] = valid
                return False
            valid.append(now)
            self._attempts[key] = valid
            return True

    def reset(self, key: str | None = None) -> None:
        """Clear rate limit history for a key or all keys."""
        with self._lock:
            if key is None:
                self._attempts.clear()
            else:
                self._attempts.pop(key, None)


# Default global auth limiter
auth_limiter = InMemoryRateLimiter(
    max_requests=settings.auth_rate_limit_requests,
    window_seconds=settings.auth_rate_limit_window_seconds,
)
