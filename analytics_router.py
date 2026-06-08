# analytics_router.py
# Place at: /app/analytics_router.py  (same level as main.py)
#
# Mount in main.py:
#   from analytics_router import analytics_router
#   app.include_router(analytics_router)

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import os

from db.models import SessionLocal
from auth_middleware import require_admin
from analytics import (
    get_active_jobs_for_analytics,
    get_all_jobs_for_analytics,
    get_alert_stats,
    get_alerts_for_job,
    get_all_recent_activity,
    get_activity_for_user,
    get_activity_summary_per_user,
    get_job_analytics_detail,
    get_price_trend,
    get_runs_for_job_analytics,
    get_site_performance,
    _safe_json,
)

analytics_router = APIRouter(prefix="/analytics", tags=["analytics"])
templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "templates")
)


# ── Page routes ────────────────────────────────────────────────────────────────

@analytics_router.get("/products", response_class=HTMLResponse, include_in_schema=False)
async def products_page(request: Request):
    require_admin(request)
    return templates.TemplateResponse("analytics_products.html", {"request": request})


@analytics_router.get("/products/{job_id}", response_class=HTMLResponse, include_in_schema=False)
async def product_detail_page(request: Request, job_id: int):
    require_admin(request)
    return templates.TemplateResponse("analytics_product_detail.html",
                                      {"request": request, "job_id": job_id})


@analytics_router.get("/users", response_class=HTMLResponse, include_in_schema=False)
async def users_activity_page(request: Request):
    require_admin(request)
    return templates.TemplateResponse("analytics_users.html", {"request": request})


@analytics_router.get("/users/{username}", response_class=HTMLResponse, include_in_schema=False)
async def user_detail_page(request: Request, username: str):
    require_admin(request)
    return templates.TemplateResponse("analytics_user_detail.html",
                                      {"request": request, "username": username})


@analytics_router.get("/sites", response_class=HTMLResponse, include_in_schema=False)
async def sites_page(request: Request):
    require_admin(request)
    return templates.TemplateResponse("analytics_sites.html", {"request": request})


# ── API: products list ─────────────────────────────────────────────────────────

@analytics_router.get("/api/products")
async def api_products(request: Request, show_deleted: bool = False):
    require_admin(request)
    db = SessionLocal()
    try:
        jobs = get_all_jobs_for_analytics(db) if show_deleted else get_active_jobs_for_analytics(db)
        result = []
        for j in jobs:
            run_count  = len(j.runs) if j.runs else 0
            alert_count = len(j.alerts) if j.alerts else 0
            result.append({
                "id":               j.id,
                "product_name":     j.product_name,
                "job_type":         j.job_type,
                "target_price":     j.target_price,
                "user_email":       j.user_email,
                "created_by":       getattr(j, "created_by_username", None) or "unknown",
                "schedule":         j.schedule_interval,
                "is_active":        j.is_active,
                "alert_sent":       j.alert_sent,
                "created_at":       j.created_at.strftime("%Y-%m-%d %H:%M") if j.created_at else None,
                "last_run_at":      j.last_run_at.strftime("%Y-%m-%d %H:%M") if j.last_run_at else None,
                "last_lowest_price": j.last_lowest_price,
                "run_count":        run_count,
                "alert_count":      alert_count,
                "sites":            _safe_json(j.selected_sites),
            })
        return JSONResponse(result)
    finally:
        db.close()


# ── API: product detail ────────────────────────────────────────────────────────

@analytics_router.get("/api/products/{job_id}")
async def api_product_detail(request: Request, job_id: int):
    require_admin(request)
    db = SessionLocal()
    try:
        job = get_job_analytics_detail(db, job_id)
        if not job:
            return JSONResponse({"error": "Not found"}, status_code=404)

        runs   = get_runs_for_job_analytics(db, job_id, limit=100)
        alerts = get_alerts_for_job(db, job_id)
        trend  = get_price_trend(db, job_id)

        runs_data = []
        for r in runs:
            results  = _safe_json(r.results_json)
            top_hits = sorted(
                [x for x in results if x.get("price")],
                key=lambda x: x.get("price", 0)
            )[:5]
            runs_data.append({
                "id":              r.id,
                "run_type":        r.run_type,
                "started_at":      r.started_at.strftime("%Y-%m-%d %H:%M") if r.started_at else None,
                "completed_at":    r.completed_at.strftime("%Y-%m-%d %H:%M") if r.completed_at else None,
                "lowest_price":    r.lowest_price,
                "lowest_site":     r.lowest_site,
                "alert_triggered": r.alert_triggered,
                "sites_checked":   _safe_json(r.sites_checked),
                "error_sites":     _safe_json(r.error_sites),
                "top_hits":        top_hits,
            })

        alerts_data = [{
            "sent_at":           a.sent_at.strftime("%Y-%m-%d %H:%M") if a.sent_at else None,
            "email_to":          a.email_to,
            "lowest_price_found": a.lowest_price_found,
            "send_status":       a.send_status,
        } for a in alerts]

        return JSONResponse({
            "job": {
                "id":            job.id,
                "product_name":  job.product_name,
                "job_type":      job.job_type,
                "target_price":  job.target_price,
                "user_email":    job.user_email,
                "created_by":    getattr(job, "created_by_username", None) or "unknown",
                "schedule":      job.schedule_interval,
                "is_active":     job.is_active,
                "alert_sent":    job.alert_sent,
                "created_at":    job.created_at.strftime("%Y-%m-%d %H:%M") if job.created_at else None,
                "last_run_at":   job.last_run_at.strftime("%Y-%m-%d %H:%M") if job.last_run_at else None,
                "last_lowest_price": job.last_lowest_price,
                "sites":         _safe_json(job.selected_sites),
            },
            "runs":   runs_data,
            "alerts": alerts_data,
            "trend":  trend,
        })
    finally:
        db.close()


# ── API: site performance ──────────────────────────────────────────────────────

@analytics_router.get("/api/sites")
async def api_site_performance(request: Request):
    require_admin(request)
    db = SessionLocal()
    try:
        return JSONResponse(get_site_performance(db))
    finally:
        db.close()


# ── API: alert stats ───────────────────────────────────────────────────────────

@analytics_router.get("/api/alert-stats")
async def api_alert_stats(request: Request):
    require_admin(request)
    db = SessionLocal()
    try:
        return JSONResponse(get_alert_stats(db))
    finally:
        db.close()


# ── API: user activity summary ─────────────────────────────────────────────────

@analytics_router.get("/api/users")
async def api_users_activity(request: Request):
    require_admin(request)
    db = SessionLocal()
    try:
        return JSONResponse(get_activity_summary_per_user(db))
    finally:
        db.close()


# ── API: single user activity ──────────────────────────────────────────────────

@analytics_router.get("/api/users/{username}")
async def api_user_activity(request: Request, username: str):
    require_admin(request)
    db = SessionLocal()
    try:
        logs = get_activity_for_user(db, username, limit=500)
        return JSONResponse([{
            "id":          l.id,
            "timestamp":   l.timestamp.strftime("%Y-%m-%d %H:%M:%S") if l.timestamp else None,
            "event_type":  l.event_type,
            "detail":      l.detail,
            "ip_address":  l.ip_address,
            "job_id":      l.job_id,
            "target_user": l.target_user,
        } for l in logs])
    finally:
        db.close()


# ── API: recent activity feed (all users) ──────────────────────────────────────

@analytics_router.get("/api/activity")
async def api_recent_activity(request: Request):
    require_admin(request)
    db = SessionLocal()
    try:
        logs = get_all_recent_activity(db, limit=200)
        return JSONResponse([{
            "id":          l.id,
            "timestamp":   l.timestamp.strftime("%Y-%m-%d %H:%M:%S") if l.timestamp else None,
            "username":    l.username,
            "event_type":  l.event_type,
            "detail":      l.detail,
            "ip_address":  l.ip_address,
            "job_id":      l.job_id,
        } for l in logs])
    finally:
        db.close()
