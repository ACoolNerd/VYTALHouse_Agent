from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status


def extract_token(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return authorization[7:].strip()
    return request.headers.get("X-Admin-Token", "").strip()


def require_admin_token(request: Request) -> None:
    token = extract_token(request)
    expected = request.app.state.settings.admin_token
    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid admin token is required.",
        )
