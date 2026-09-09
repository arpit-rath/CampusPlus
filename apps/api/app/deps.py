"""Shared FastAPI dependencies — currently just admin access control.

There is no user table and no login flow in this project; adding one would
be a lot of surface area for a demo whose point is the intelligence layer.
What the project *did* have was nothing at all: any caller could resolve a
complaint, re-route it to another department, or delete it outright.

So: a single shared secret in `ADMIN_TOKEN`, sent as `X-Admin-Token`, gates
every administrative action. When `ADMIN_TOKEN` is unset the API runs open,
because a demo that requires a header nobody set is a demo that fails on
stage — but that state is reported explicitly as `admin_auth: "disabled"`
on `/health` rather than being an invisible hole. Set the variable and it
is enforced everywhere, immediately.

Comparison uses `secrets.compare_digest` so the check does not leak the
token through response timing.
"""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from app.config import get_settings


async def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    """Reject the request unless it carries the configured admin token.

    A no-op when `ADMIN_TOKEN` is empty (see module docstring).
    """
    settings = get_settings()
    expected = settings.admin_token
    if not expected:
        return

    if not x_admin_token or not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Admin token missing or invalid",
            headers={"WWW-Authenticate": "X-Admin-Token"},
        )


def admin_auth_enabled() -> bool:
    return bool(get_settings().admin_token)
