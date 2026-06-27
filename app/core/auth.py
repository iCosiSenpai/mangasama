"""HTTP Basic auth helper for the single-admin gate.

The admin account is created by the first-run web setup and persisted in
``/config/admin.json``. We use Basic auth because OPDS readers (Moon+ Reader,
KyBook, …) and browsers support it natively. The username is no longer ignored:
it must match the one chosen during setup, and the password is compared in
constant time against a bcrypt hash.
"""

from __future__ import annotations

from app.core.setup_state import verify_basic_auth


def check_basic_auth(authorization_header: str | None, password: str) -> bool:
    """Legacy constant-time check against a plain password.

    Kept for callers that still pass the env-configured admin password; new
    code should use :func:`verify_admin_auth`.
    """
    return verify_basic_auth(authorization_header)


def verify_admin_auth(authorization_header: str | None) -> bool:
    """Return True iff the ``Authorization: Basic`` header matches ``admin.json``.

    Fails closed: missing/malformed header, missing admin file, wrong username or
    wrong password all return False.
    """
    return verify_basic_auth(authorization_header)


__all__ = ["check_basic_auth", "verify_admin_auth"]
