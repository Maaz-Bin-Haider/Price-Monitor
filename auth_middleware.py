# auth_middleware.py
# Place this file at: /app/auth_middleware.py  (same level as main.py)
#
# Wraps every single request.  Anything that isn't /login or /static
# is redirected to /login unless a valid JWT cookie is present.

from fastapi import HTTPException, Request, status
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from auth import COOKIE_NAME, decode_token

# ── Paths that do NOT require a login ─────────────────────────────────────────
PUBLIC_PATHS = [
    "/login",
    "/auth/login",
    "/auth/logout",
    "/favicon.ico",
    "/static",
    "/health",          # keep health-check public for Docker / monitoring
]

def _is_public(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") or path.startswith(p + "?")
               for p in PUBLIC_PATHS)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if _is_public(request.url.path):
            return await call_next(request)

        token = request.cookies.get(COOKIE_NAME)
        if not token:
            return RedirectResponse(url="/login", status_code=302)

        payload = decode_token(token)
        if payload is None:
            # Expired or tampered — clear cookie and redirect
            response = RedirectResponse(url="/login", status_code=302)
            response.delete_cookie(COOKIE_NAME)
            return response

        # Attach to request.state so routes can read it without re-decoding
        request.state.username = payload.get("sub")
        request.state.is_admin = payload.get("admin", False)

        return await call_next(request)


# ── FastAPI dependencies (use in route handlers) ───────────────────────────────

def get_current_user(request: Request) -> dict:
    """Returns {"username": ..., "is_admin": ...} or raises 401."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    return {"username": payload["sub"], "is_admin": payload.get("admin", False)}

def require_admin(request: Request) -> dict:
    """Returns user dict or raises 403 if not admin."""
    user = get_current_user(request)
    if not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
