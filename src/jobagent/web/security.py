"""Password hashing (PBKDF2, stdlib), signed session cookies and CSRF tokens."""
from __future__ import annotations
import base64
import hashlib
import hmac
import os
import secrets
import time

ITERATIONS = 240_000


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, ITERATIONS)
    return f"pbkdf2${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, it, salt, dk = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", pw.encode(), base64.b64decode(salt), int(it))
        return hmac.compare_digest(calc, base64.b64decode(dk))
    except Exception:  # noqa: BLE001
        return False


class Signer:
    """Signs 'uid|csrf|expiry' so the cookie can't be forged or edited."""
    def __init__(self, secret: str, max_age: int = 14 * 86400):
        self.secret, self.max_age = secret.encode(), max_age

    def _sig(self, payload: str) -> str:
        return hmac.new(self.secret, payload.encode(), hashlib.sha256).hexdigest()

    def make(self, user_id: str) -> tuple[str, str]:
        csrf = secrets.token_urlsafe(16)
        payload = f"{user_id}|{csrf}|{int(time.time()) + self.max_age}"
        return f"{payload}|{self._sig(payload)}", csrf

    def read(self, cookie: str | None) -> tuple[str, str] | None:
        if not cookie:
            return None
        try:
            uid, csrf, exp, sig = cookie.split("|")
        except ValueError:
            return None
        if not hmac.compare_digest(self._sig(f"{uid}|{csrf}|{exp}"), sig) or int(exp) < time.time():
            return None
        return uid, csrf


class RateLimiter:
    """Tiny in-memory limiter for login attempts (per key, sliding window)."""
    def __init__(self, limit: int = 8, window: int = 300):
        self.limit, self.window, self.hits = limit, window, {}

    def allow(self, key: str) -> bool:
        now = time.time()
        hits = [h for h in self.hits.get(key, []) if now - h < self.window]
        ok = len(hits) < self.limit
        if ok:
            hits.append(now)
        self.hits[key] = hits
        return ok
