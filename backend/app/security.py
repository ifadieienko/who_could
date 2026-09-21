import base64
import hashlib
import hmac
import json
import secrets
import time
from binascii import Error as BinasciiError
from typing import Any

from .config import settings

SECRET = settings.secret
SESSION_COOKIE_NAME = "who_could_session"
TOKEN_TTL_SECONDS = 60 * 60 * 24


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 210_000)
    return f"pbkdf2_sha256${salt}${base64.b64encode(digest).decode('ascii')}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        method, salt, digest_b64 = stored_hash.split("$", 2)
    except ValueError:
        return False
    if method != "pbkdf2_sha256":
        return False
    expected = base64.b64decode(digest_b64.encode("ascii"))
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 210_000)
    return hmac.compare_digest(actual, expected)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64url(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def create_token(user_id: int) -> str:
    now = int(time.time())
    payload = {"sub": user_id, "iat": now, "exp": now + TOKEN_TTL_SECONDS}
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(SECRET.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64url(signature)}"


def read_token(token: str) -> dict[str, Any] | None:
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(SECRET.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
        actual = _unb64url(signature)
        if not hmac.compare_digest(actual, expected):
            return None
        payload = json.loads(_unb64url(body).decode("utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("sub"), int):
            return None
        now = int(time.time())
        if int(payload.get("exp", 0)) < now or int(payload.get("iat", now)) > now + 60:
            return None
        return payload
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError, BinasciiError):
        return None
