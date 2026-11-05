"""Admin authentication helpers.

Passwords are verified against a salted PBKDF2-HMAC-SHA256 hash using a
constant-time comparison. Failed logins are rate limited with a lockout, and
sessions expire after inactivity.

Limitations (see README): the limiter is in-process memory, so it resets when
the Streamlit server restarts and is not shared across multiple instances.
This is a single shared admin password, not per-user accounts.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from typing import Callable, Mapping, Optional

ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 600_000  # OWASP guidance for PBKDF2-HMAC-SHA256


def hash_password(password: str, iterations: int = DEFAULT_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return "$".join(
        (
            ALGORITHM,
            str(iterations),
            base64.b64encode(salt).decode(),
            base64.b64encode(digest).decode(),
        )
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_b64, digest_b64 = stored.split("$")
        if algo != ALGORITHM:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def check_admin_password(password: str, admin_secrets: Mapping[str, str]) -> bool:
    """Verify against ``password_hash``; fall back to legacy ``password``.

    The legacy plaintext entry keeps existing deployments working until they
    run ``scripts/hash_password.py`` and switch to ``password_hash``.
    """
    stored_hash = admin_secrets.get("password_hash")
    if stored_hash:
        return verify_password(password, stored_hash)
    legacy = admin_secrets.get("password")
    if legacy:
        return hmac.compare_digest(password.encode(), str(legacy).encode())
    return False


def uses_legacy_password(admin_secrets: Mapping[str, str]) -> bool:
    return not admin_secrets.get("password_hash") and bool(admin_secrets.get("password"))


class LoginLimiter:
    """Lock out after ``max_failures`` failures within ``window`` seconds."""

    def __init__(
        self,
        max_failures: int = 5,
        window: float = 300,
        lockout: float = 300,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.max_failures = max_failures
        self.window = window
        self.lockout = lockout
        self.clock = clock
        self._failures: list[float] = []
        self._locked_until: Optional[float] = None

    def seconds_locked(self) -> int:
        if self._locked_until is None:
            return 0
        remaining = self._locked_until - self.clock()
        if remaining <= 0:
            self._locked_until = None
            self._failures.clear()
            return 0
        return int(remaining) + 1

    def record_failure(self) -> None:
        now = self.clock()
        self._failures = [t for t in self._failures if now - t < self.window]
        self._failures.append(now)
        if len(self._failures) >= self.max_failures:
            self._locked_until = now + self.lockout

    def record_success(self) -> None:
        self._failures.clear()
        self._locked_until = None


def session_expired(
    last_active: Optional[float], now: float, timeout: float = 1800
) -> bool:
    return last_active is None or now - last_active > timeout
