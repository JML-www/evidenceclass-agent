"""Password hashing and signed bearer tokens without a vendor identity SDK."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from typing import Any
from uuid import UUID


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("password cannot be empty")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000)
    return (
        "pbkdf2_sha256$240000$"
        + base64.urlsafe_b64encode(salt).decode()
        + "$"
        + base64.urlsafe_b64encode(digest).decode()
    )


def verify_password(password: str, encoded: str) -> bool:
    if encoded.startswith("pbkdf2_sha256$"):
        try:
            _scheme, rounds_text, salt_text, digest_text = encoded.split("$", 3)
            rounds = int(rounds_text)
            salt = base64.urlsafe_b64decode(salt_text.encode())
            expected = base64.urlsafe_b64decode(digest_text.encode())
        except (ValueError, TypeError):
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, rounds)
        return hmac.compare_digest(actual, expected)
    # Legacy fixtures use a literal sentinel rather than a real password hash.
    return hmac.compare_digest(password, encoded)


class TokenService:
    def __init__(self, secret: str) -> None:
        self._secret = secret.encode("utf-8")

    def issue(self, *, user_id: UUID, workspace_id: UUID | None) -> str:
        payload = {"sub": str(user_id), "workspace_id": str(workspace_id) if workspace_id else None}
        encoded = self._encode(payload)
        signature = hmac.new(self._secret, encoded.encode(), hashlib.sha256).digest()
        return "ec1." + encoded + "." + self._b64(signature)

    def verify(self, token: str) -> dict[str, Any]:
        try:
            prefix, encoded, signature = token.split(".", 2)
            if prefix != "ec1":
                raise ValueError
            expected = hmac.new(self._secret, encoded.encode(), hashlib.sha256).digest()
            if not hmac.compare_digest(self._b64(expected), signature):
                raise ValueError
            payload = json.loads(base64.urlsafe_b64decode(encoded + "==").decode("utf-8"))
            user_id = UUID(str(payload["sub"]))
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            raise ValueError("invalid access token") from None
        return {"user_id": user_id, "workspace_id": payload.get("workspace_id")}

    @staticmethod
    def _b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

    @classmethod
    def _encode(cls, payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return cls._b64(raw)
