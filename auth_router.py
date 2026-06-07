# auth_router.py
# Place this file at: /app/auth_router.py  (same level as main.py)
#
# Uses your existing SessionLocal from db/models.py — synchronous SQLAlchemy,
# same pattern as the rest of your project.

from typing import Optional

from fastapi import APIRouter, Depends, Form, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import os

from db.models import SessionLocal       # ← your existing session factory
from auth import (
    COOKIE_NAME, TOKEN_EXPIRE,
    authenticate_user, create_access_token,
    create_user, delete_user_by_id, get_user,
    list_users, list_locked_ips, toggle_user_active, unlock_ip,
)
from auth_middleware import get_current_user, require_admin

auth_router = APIRouter(tags=["auth"])
templates   = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "templates")
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
    finally:
        db.close()

    if error:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": error},
            status_code=401,
        )

    token    = create_access_token(user.username, user.is_admin)
    redirect = "/admin" if user.is_admin else "/"
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
async def logout():
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
    is_admin: bool          = Form(False),
):
    admin = require_admin(request)
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
            email      = email or None,
            is_admin   = is_admin,
            created_by = admin["username"],
        )
    finally:
        db.close()

    return JSONResponse({"id": user.id, "username": user.username, "is_admin": user.is_admin},
                        status_code=201)


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
    return JSONResponse([
        {
            "ip":           r.ip_address,
            "attempts":     r.attempt_count,
            "locked_until": r.locked_until.strftime("%Y-%m-%d %H:%M UTC") if r.locked_until else None,
        }
        for r in rows
    ])


# ── Admin API: unlock IP ───────────────────────────────────────────────────────

@auth_router.post("/auth/admin/unlock-ip")
async def admin_unlock_ip(request: Request, ip: str = Form(...)):
    require_admin(request)
    db = SessionLocal()
    try:
        unlock_ip(db, ip)
    finally:
        db.close()
    return JSONResponse({"unlocked": ip})
