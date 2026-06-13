# auth_router.py
# auth/router.py — FastAPI router for login/logout and admin user management
#
# Uses your existing SessionLocal from db/models.py — synchronous SQLAlchemy,
# same pattern as the rest of your project.

from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import os

from db.models import SessionLocal       # ← your existing session factory
from auth.core import (
    COOKIE_NAME, TOKEN_EXPIRE,
    authenticate_user, create_access_token,
    create_user, delete_user_by_id, get_user,
    list_users, list_locked_ips, toggle_user_active, unlock_ip,
)
from auth.middleware import get_current_user, require_admin
from analytics.queries import log_activity

auth_router = APIRouter(tags=["auth"])
templates   = Jinja2Templates(
    # __file__ is now auth/router.py — go up one level to reach /app/templates/
    directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
)


# ── DB dependency (mirrors your existing project pattern) ──────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Real client IP (works behind Nginx + Cloudflare) ──────────────────────────

def _client_ip(request: Request) -> str:
    for header in ("cf-connecting-ip", "x-real-ip", "x-forwarded-for"):
        val = request.headers.get(header)
        if val:
            return val.split(",")[0].strip()
    return request.client.host


# ── Login page ─────────────────────────────────────────────────────────────────

@auth_router.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@auth_router.post("/auth/login")
async def login_submit(
    request:  Request,
    username: str = Form(...),
    password: str = Form(...),
):
    db  = SessionLocal()
    ip  = _client_ip(request)
    try:
        user, error = authenticate_user(db, ip, username, password)
        # Read attributes while session is still open — accessing them after
        # db.close() causes DetachedInstanceError (SQLAlchemy expires on close)
        if user:
            _username = user.username
            _is_admin = user.is_admin
        else:
            _username = None
            _is_admin = False
    finally:
        db.close()

    if error:
        log_activity(
            username   = username.strip() if username else "unknown",
            event_type = "login_failed",
            detail     = error,
            ip_address = ip,
        )
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": error},
            status_code=401,
        )

    log_activity(
        username   = _username,
        event_type = "login",
        detail     = "Successful login",
        ip_address = ip,
    )
    token    = create_access_token(_username, _is_admin)
    redirect = "/admin" if _is_admin else "/"
    response = RedirectResponse(url=redirect, status_code=302)
    response.set_cookie(
        key      = COOKIE_NAME,
        value    = token,
        httponly = True,        # JS cannot read it (XSS protection)
        secure   = True,        # HTTPS only
        samesite = "lax",
        max_age  = TOKEN_EXPIRE * 60,
    )
    return response


@auth_router.get("/auth/logout")
async def logout(request: Request):
    try:
        from auth.core import COOKIE_NAME as _cn, decode_token as _dt
        _token = request.cookies.get(_cn)
        if _token:
            _p = _dt(_token)
            if _p:
                log_activity(username=_p.get("sub","unknown"), event_type="logout", detail="Signed out")
    except Exception:
        pass
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


# ── Admin dashboard page ───────────────────────────────────────────────────────

@auth_router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_page(request: Request):
    require_admin(request)   # raises 403 if not admin
    return templates.TemplateResponse("admin.html", {"request": request})


# ── Admin API: list users ──────────────────────────────────────────────────────

@auth_router.get("/auth/admin/users")
async def admin_list_users(request: Request):
    require_admin(request)
    db = SessionLocal()
    try:
        users = list_users(db)
    finally:
        db.close()
    return JSONResponse([
        {
            "id":         u.id,
            "username":   u.username,
            "email":      u.email,
            "is_admin":   u.is_admin,
            "is_active":  u.is_active,
            "created_at": u.created_at.strftime("%Y-%m-%d") if u.created_at else None,
            "created_by": u.created_by,
        }
        for u in users
    ])


# ── Admin API: create user ─────────────────────────────────────────────────────

@auth_router.post("/auth/admin/users", status_code=201)
async def admin_create_user(
    request:  Request,
    username: str           = Form(...),
    password: str           = Form(...),
    email:    Optional[str] = Form(None),
    # HTML checkboxes send "on" when ticked and nothing when unticked.
    # Declaring as bool causes FastAPI to reject missing values with 422.
    # We read it as an optional string and convert manually.
    is_admin_raw: Optional[str] = Form(None, alias="is_admin"),
):
    admin = require_admin(request)

    # Normalise the checkbox value
    is_admin = is_admin_raw in ("on", "true", "True", "1", True)

    username = username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username cannot be empty")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    db = SessionLocal()
    try:
        if get_user(db, username):
            raise HTTPException(status_code=400, detail="Username already exists")
        user = create_user(
            db         = db,
            username   = username,
            password   = password,
            email      = email.strip() if email else None,
            is_admin   = is_admin,
            created_by = admin["username"],
        )
        log_activity(
            username    = admin["username"],
            event_type  = "user_created",
            detail      = f"Created user '{username}'" + (" (admin)" if is_admin else ""),
            target_user = username,
        )
        return JSONResponse(
            {"id": user.id, "username": user.username, "is_admin": user.is_admin},
            status_code=201,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create user: {e}")
    finally:
        db.close()


# ── Admin API: toggle active ───────────────────────────────────────────────────

@auth_router.patch("/auth/admin/users/{user_id}/toggle")
async def admin_toggle_user(user_id: int, request: Request):
    require_admin(request)
    db = SessionLocal()
    try:
        user = toggle_user_active(db, user_id)
    finally:
        db.close()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        _actor = require_admin(request)
        log_activity(
            username    = _actor["username"],
            event_type  = "user_toggled",
            detail      = f"Set user '{user.is_active}' active={user.is_active}",
            target_user = str(user_id),
        )
    except Exception:
        pass
    return JSONResponse({"id": user.id, "is_active": user.is_active})


# ── Admin API: delete user ─────────────────────────────────────────────────────

@auth_router.delete("/auth/admin/users/{user_id}")
async def admin_delete_user(user_id: int, request: Request):
    admin = require_admin(request)
    db = SessionLocal()
    try:
        # Prevent self-deletion
        all_users = list_users(db)
        target    = next((u for u in all_users if u.id == user_id), None)
        if target and target.username == admin["username"]:
            raise HTTPException(status_code=400, detail="You cannot delete your own account")
        ok = delete_user_by_id(db, user_id)
    finally:
        db.close()
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    log_activity(
        username    = admin["username"],
        event_type  = "user_deleted",
        detail      = f"Deleted user #{user_id}",
        target_user = str(user_id),
    )
    return JSONResponse({"deleted": True})


# ── Admin API: list locked IPs ─────────────────────────────────────────────────

@auth_router.get("/auth/admin/locked-ips")
async def admin_locked_ips(request: Request):
    require_admin(request)
    db = SessionLocal()
    try:
        rows = list_locked_ips(db)
    finally:
        db.close()
    now = datetime.utcnow()
    return JSONResponse([
        {
            "ip":           r.ip_address,
            "attempts":     r.attempt_count,
            "is_locked":    bool(r.locked_until and r.locked_until > now),
            "locked_until": r.locked_until.strftime("%Y-%m-%d %H:%M UTC") if r.locked_until else None,
            "last_attempt": r.last_attempt.strftime("%Y-%m-%d %H:%M UTC") if r.last_attempt else None,
        }
        for r in rows
    ])


# ── Admin API: unlock IP ───────────────────────────────────────────────────────

@auth_router.post("/auth/admin/unlock-ip")
async def admin_unlock_ip(request: Request, ip: str = Form(...)):
    require_admin(request)
    ip = ip.strip()
    db = SessionLocal()
    try:
        unlock_ip(db, ip)
    finally:
        db.close()
    try:
        _actor = require_admin(request)
        log_activity(
            username   = _actor["username"],
            event_type = "ip_unlocked",
            detail     = f"Unlocked IP: {ip}",
        )
    except Exception:
        pass
    return JSONResponse({"unlocked": ip})
