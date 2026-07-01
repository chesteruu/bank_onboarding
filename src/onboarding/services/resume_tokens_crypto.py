"""Crypto helpers for resume tokens.

The token handed to the user is an HMAC over ``application_id:salt`` keyed by a
server-side secret. Only the SHA-256 *hash* of that token and the (non-secret)
salt are stored, so a database dump alone cannot produce a valid token without
the secret. Because the token is deterministic given ``(secret, app_id, salt)``,
the resume link can be regenerated for display without storing the raw token.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from uuid import UUID


def new_salt() -> str:
    return secrets.token_hex(16)


def mint_token(secret: str, application_id: UUID, salt: str) -> str:
    message = f"{application_id}:{salt}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
