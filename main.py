from dotenv import load_dotenv
load_dotenv()
import json
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config import SITES, settings
from db.crud import (
    complete_run,
    create_alert_log,
    create_job,
    create_run,
    get_all_active_jobs,
    get_job_by_id,
    get_runs_for_job,
    soft_delete_job,
    update_alert_sent,
    update_job,
    update_last_run,
)
from db.models import Base, engine
from notifications.email import send_alert_email, send_availability_email
from scheduler import (
    cancel_job,
    get_scheduler,
    register_job,
    restore_all_jobs,
    run_scheduled_job,
    _get_next_run_time,
)
from scraper.runner import run_search, run_availability_search

# ── Auth ───────────────────────────────────────────────────────────────────
from auth_middleware import AuthMiddleware
from auth_router import auth_router
import auth_models  # noqa — registers AuthUser/AuthLoginAttempt with SQLAlchemy Base

app = FastAPI(title="Price Monitor")

# Login wall — must be added BEFORE any routes are registered
app.add_middleware(AuthMiddleware)

# Auth routes: /login  /auth/login  /auth/logout  /admin  /auth/admin/*
app.include_router(auth_router)

# ── Templates ──────────────────────────────────────────────────────────────
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# Build a lookup dict: domain → site info (for template filters)
SITES_BY_DOMAIN = {s["domain"]: s for s in SITES}


def _from_json(val):
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return []
    return val or []


def _time_ago(dt: Optional[datetime]) -> str:
    if not dt:
        return "Never"
    now = datetime.utcnow()
    diff = now - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days == 1:
        return "1 day ago"
    return f"{days} days ago"


def _datetime_fmt(dt: Optional[datetime]) -> str:
    if not dt:
        return "—"
    return dt.strftime("%d %b %Y %H:%M")


def _selectattr_geo(domains: list, geo: str) -> list:
    """Filter a list of domain strings by geo."""
    return [d for d in domains if SITES_BY_DOMAIN.get(d, {}).get("geo") == geo]


def _site_names_from_domains(domains: list) -> list:
    """Convert domain strings to site names for tooltip."""
    return [SITES_BY_DOMAIN.get(d, {}).get("name", d) for d in domains]


# Register Jinja2 filters
templates.env.filters["from_json"] = _from_json
templates.env.filters["time_ago"] = _time_ago
templates.env.filters["datetime_fmt"] = _datetime_fmt
templates.env.filters["selectattr_geo"] = _selectattr_geo
templates.env.filters["site_names_from_domains"] = _site_names_from_domains


# ── Startup / Shutdown ─────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    # Create all tables: existing (watchlist_jobs etc.) + new auth tables
    Base.metadata.create_all(bind=engine)
    restore_all_jobs()
    get_scheduler().start()
    print("[APP] Price Monitor started")

    # # ── Seed first admin if no users exist ────────────────────────────────
    # from db.models import SessionLocal
    # from auth import list_users, create_user
    # db = SessionLocal()
    # try:
    #     if not list_users(db):
    #         create_user(
    #             db         = db,
    #             username   = "admin",
    #             password   = "ChangeMe123!",   # ← change this after first login
    #             email      = None,
    #             is_admin   = True,
    #             created_by = "system",
    #         )
    #         print("[AUTH] First admin created  username=admin  password=ChangeMe123!")
    #         print("[AUTH] ⚠  Change this password immediately via /admin")
    # finally:
    #     db.close()
    # WITH this:
    # ── Seed first admin if no users exist ────────────────────────────────
    try:
        from db.models import SessionLocal
        from auth import list_users, create_user
        _db = SessionLocal()
        try:
            if not list_users(_db):
                create_user(
                    db         = _db,
                    username   = "admin",
                    password   = "Admin1234",
                    email      = None,
                    is_admin   = True,
                    created_by = "system",
                )
                print("[AUTH] First admin created  username=admin  password=Admin1234")
                print("[AUTH] Change this password immediately via /admin")
        finally:
            _db.close()
    except Exception as _e:
        print(f"[AUTH] Warning: could not seed admin user: {_e}")


@app.on_event("shutdown")
async def shutdown_event():
    get_scheduler().shutdown(wait=False)
    print("[APP] Scheduler shut down")


# ── Routes ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    jobs = get_all_active_jobs()
    return templates.TemplateResponse("index.html", {"request": request, "jobs": jobs})


@app.get("/add", response_class=HTMLResponse)
async def add_form(request: Request):
    sites_au = [s for s in SITES if s["geo"] == "au"]
    sites_nz = [s for s in SITES if s["geo"] == "nz"]
    return templates.TemplateResponse("add.html", {
        "request": request,
        "sites_au": sites_au,
        "sites_nz": sites_nz,
    })


@app.post("/add")
async def add_submit(
    request: Request,
    product_name: str = Form(...),
    target_price: float = Form(...),
    user_email: str = Form(...),
    schedule_interval: str = Form(...),
):
    form = await request.form()
    selected_sites = form.getlist("selected_sites")

    if not selected_sites:
        sites_au = [s for s in SITES if s["geo"] == "au"]
        sites_nz = [s for s in SITES if s["geo"] == "nz"]
        return templates.TemplateResponse("add.html", {
            "request": request,
            "sites_au": sites_au,
            "sites_nz": sites_nz,
            "error": "Please select at least one site.",
        }, status_code=400)

    job = create_job({
        "job_type": "price_watch",
        "product_name": product_name,
        "target_price": target_price,
        "user_email": user_email,
        "schedule_interval": schedule_interval,
        "selected_sites": selected_sites,
    })

    if job:
        register_job(job)

    return RedirectResponse(url="/", status_code=303)


@app.get("/add-scout", response_class=HTMLResponse)
async def add_scout_form(request: Request):
    sites_au = [s for s in SITES if s["geo"] == "au"]
    sites_nz = [s for s in SITES if s["geo"] == "nz"]
    return templates.TemplateResponse("add_scout.html", {
        "request": request,
        "sites_au": sites_au,
        "sites_nz": sites_nz,
    })


@app.post("/add-scout")
async def add_scout_submit(
    request: Request,
    product_name: str = Form(...),
    user_email: str = Form(...),
    schedule_interval: str = Form(...),
):
    form = await request.form()
    selected_sites = form.getlist("selected_sites")

    if not selected_sites:
        sites_au = [s for s in SITES if s["geo"] == "au"]
        sites_nz = [s for s in SITES if s["geo"] == "nz"]
        return templates.TemplateResponse("add_scout.html", {
            "request": request,
            "sites_au": sites_au,
            "sites_nz": sites_nz,
            "error": "Please select at least one site.",
        }, status_code=400)

    job = create_job({
        "job_type": "availability_scout",
        "product_name": product_name,
        "target_price": None,
        "user_email": user_email,
        "schedule_interval": schedule_interval,
        "selected_sites": selected_sites,
    })

    if job:
        register_job(job)

    return RedirectResponse(url="/", status_code=303)


@app.get("/job/{job_id}", response_class=HTMLResponse)
async def job_detail(request: Request, job_id: int):
    job = get_job_by_id(job_id)
    if not job or not job.is_active:
        return RedirectResponse(url="/", status_code=302)
    runs = get_runs_for_job(job_id, limit=50)
    return templates.TemplateResponse("detail.html", {
        "request": request,
        "job": job,
        "runs": runs,
    })


@app.post("/job/{job_id}/run")
async def run_now(job_id: int):
    job = get_job_by_id(job_id)
    if not job or not job.is_active:
        return JSONResponse({"error": "Job not found"}, status_code=404)

    selected_sites = _from_json(job.selected_sites)
    run = create_run(job_id, "instant")
    if not run:
        return JSONResponse({"error": "Could not create run"}, status_code=500)

    job_type = getattr(job, "job_type", None) or "price_watch"

    try:
        if job_type == "availability_scout":
            result = await run_availability_search(
                job_id=job_id,
                product_name=job.product_name,
                selected_sites=selected_sites,
            )
        else:
            result = await run_search(
                job_id=job_id,
                product_name=job.product_name,
                target_price=job.target_price,
                selected_sites=selected_sites,
            )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    alert_triggered = False
    job = get_job_by_id(job_id)  # refresh

    if job:
        if job_type == "availability_scout":
            success = await send_availability_email(job, result.get("available_sites", []))
            create_alert_log({
                "job_id": job_id,
                "run_result_id": run.id,
                "email_to": job.user_email,
                "sites_below_target": result.get("available_sites", []),
                "lowest_price_found": result.get("lowest_price") or 0,
                "send_status": "sent" if success else "failed",
            })
            alert_triggered = success
        else:
            if result["should_alert"] and not job.alert_sent:
                success = await send_alert_email(job, result["below_target"])
                create_alert_log({
                    "job_id": job_id,
                    "run_result_id": run.id,
                    "email_to": job.user_email,
                    "sites_below_target": result["below_target"],
                    "lowest_price_found": result["lowest_price"] or 0,
                    "send_status": "sent" if success else "failed",
                })
                update_alert_sent(job_id, True)
                alert_triggered = True
            elif not result["should_alert"] and job.alert_sent:
                update_alert_sent(job_id, False)

    complete_run(run.id, {
        "results": result.get("results", []),
        "sites_checked": result.get("sites_checked", []),
        "lowest_price": result.get("lowest_price"),
        "lowest_site": result.get("lowest_site"),
        "alert_triggered": alert_triggered,
        "error_sites": result.get("error_sites", []),
    })

    next_run = _get_next_run_time(job.schedule_interval if job else "24h")
    update_last_run(job_id, result.get("lowest_price"), next_run)

    return JSONResponse({"run_id": run.id, "job_id": job_id})


@app.get("/job/{job_id}/edit", response_class=HTMLResponse)
async def edit_form(request: Request, job_id: int):
    job = get_job_by_id(job_id)
    if not job or not job.is_active:
        return RedirectResponse(url="/", status_code=302)
    sites_au = [s for s in SITES if s["geo"] == "au"]
    sites_nz = [s for s in SITES if s["geo"] == "nz"]
    return templates.TemplateResponse("edit.html", {
        "request": request,
        "job": job,
        "sites_au": sites_au,
        "sites_nz": sites_nz,
    })


@app.post("/job/{job_id}/edit")
async def edit_submit(
    request: Request,
    job_id: int,
    product_name: str = Form(...),
    target_price: Optional[float] = Form(None),
    user_email: str = Form(...),
    schedule_interval: str = Form(...),
):
    form = await request.form()
    selected_sites = form.getlist("selected_sites")

    update_job(job_id, {
        "product_name": product_name,
        "target_price": target_price,
        "user_email": user_email,
        "schedule_interval": schedule_interval,
        "selected_sites": selected_sites,
    })

    cancel_job(job_id)
    job = get_job_by_id(job_id)
    if job:
        register_job(job)

    return RedirectResponse(url=f"/job/{job_id}", status_code=303)


@app.post("/job/{job_id}/delete")
async def delete_job(job_id: int):
    soft_delete_job(job_id)
    cancel_job(job_id)
    return RedirectResponse(url="/", status_code=303)


@app.get("/health")
async def health():
    scheduler = get_scheduler()
    return JSONResponse({
        "status": "ok",
        "scheduler_running": scheduler.running,
    })
