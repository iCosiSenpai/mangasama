"""HTTP Basic auth helper for the single-admin gate.

Enabled via `AUTH_ENABLED=true` + `ADMIN_PASSWORD=...`. We use Basic auth
because OPDS readers (Moon+ Reader, KyBook, …) and browsers support it
natively. The username is ignored (single-admin model); only the password
matters, compared in constant time.
"""

from __future__ import annotations

import base64
import binascii
import secrets


def check_basic_auth(authorization_header: str | None, password: str) -> bool:
    """Return True iff the `Authorization: Basic` header carries `password`.

    Fails closed: a missing/malformed header, or an empty configured
    password, returns False.
    """
    if not authorization_header or not password:
        return False
    scheme, _, b64 = authorization_header.partition(" ")
    if scheme.lower() != "basic" or not b64:
        return False
    try:
        decoded = base64.b64decode(b64, validate=True).decode("utf-8")
    except (binascii.Error, ValueError):
        return False
    _, _, supplied = decoded.partition(":")  # "user:pass" → pass
    return secrets.compare_digest(supplied, password)


__all__ = ["check_basic_auth"]
