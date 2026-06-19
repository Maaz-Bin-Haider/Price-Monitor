from dotenv import load_dotenv
load_dotenv()
import json
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from config import SITES, settings
from db.crud import (
    complete_run,
    complete_site_test_run,
    create_alert_log,
    create_company,
    create_job,
    create_run,
    create_site_test_run,
    delete_company,
    get_all_active_jobs,
    get_all_companies,
    get_companies_with_active_jobs,
    get_job_by_id,
    get_recent_site_test_runs,
    get_runs_for_job,
    get_site_test_run,
    seed_default_companies,
    soft_delete_job,
    update_alert_sent,
    update_job,
    update_last_run,
    update_site_test_progress,
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

# ── Site testing ───────────────────────────────────────────────────────────
from testers_and_fixers.test_engine import run_site_tests, select_sites, summarize, DEFAULT_TEST_PRODUCT
from testers_and_fixers.pdf_report import generate_pdf_report

# ── Auth ───────────────────────────────────────────────────────────────────
from auth.middleware import AuthMiddleware
from auth.router import auth_router
from auth import models as auth_models  # noqa — registers AuthUser/AuthLoginAttempt with Base

# ── Analytics ──────────────────────────────────────────────────────────────
from analytics.router import analytics_router
from analytics import models as analytics_models  # noqa — registers ActivityLog with Base
from analytics.queries import log_activity

app = FastAPI(title="Price Monitor")

# Login wall — must be added BEFORE any routes are registered
app.add_middleware(AuthMiddleware)

# Auth routes: /login  /auth/login  /auth/logout  /admin  /auth/admin/*
app.include_router(auth_router)

# Analytics routes: /analytics/products  /analytics/users  /analytics/sites
app.include_router(analytics_router)

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
    return [d for d in domains if SITES_BY_DOMAIN.get(d, {}).get("geo") == geo]


def _site_names_from_domains(domains: list) -> list:
    return [SITES_BY_DOMAIN.get(d, {}).get("name", d) for d in domains]


# Register Jinja2 filters
templates.env.filters["from_json"]               = _from_json
templates.env.filters["time_ago"]                = _time_ago
templates.env.filters["datetime_fmt"]            = _datetime_fmt
templates.env.filters["selectattr_geo"]          = _selectattr_geo
templates.env.filters["site_names_from_domains"] = _site_names_from_domains


# ── Startup / Shutdown ─────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    # ── Step 1: Create any missing tables ─────────────────────────────────
    # create_all() is safe — it never drops or modifies existing tables/data.
    # It creates: companies (new), watchlist_jobs, run_results, alert_log,
    # auth tables, analytics tables.
    Base.metadata.create_all(bind=engine)

    # ── Step 2: Column migrations — MUST run before restore_all_jobs() ────
    # restore_all_jobs() issues a SELECT that includes every ORM column.
    # If a column doesn't exist yet in the live DB the query crashes.
    # We use SQLAlchemy inspect() so this works on both Postgres and SQLite.
    try:
        from sqlalchemy import text as _text, inspect as _inspect
        _existing = {c["name"] for c in _inspect(engine).get_columns("watchlist_jobs")}

        with engine.connect() as _conn:
            if "created_by_username" not in _existing:
                _conn.execute(_text(
                    "ALTER TABLE watchlist_jobs ADD COLUMN"
                    " created_by_username VARCHAR(64) DEFAULT 'unknown'"
                ))
                print("[MIGRATE] Added created_by_username column")

            if "company_id" not in _existing:
                _conn.execute(_text(
                    "ALTER TABLE watchlist_jobs ADD COLUMN"
                    " company_id INTEGER REFERENCES companies(id)"
                ))
                print("[MIGRATE] Added company_id column")

            _conn.commit()
    except Exception as _e:
        print(f"[MIGRATE] Column migration error: {_e}")

    # ── Step 3: Restore scheduler — all columns now guaranteed to exist ───
    restore_all_jobs()
    get_scheduler().start()

    # ── Step 4: Seed default companies ────────────────────────────────────
    seed_default_companies()

    print("[APP] Price Monitor started")

    # ── Seed first admin if no users exist ────────────────────────────────
    from db.models import SessionLocal
    from auth.core import list_users, create_user
    db = SessionLocal()
    try:
        if not list_users(db):
            create_user(
                db         = db,
                username   = "admin",
                password   = "ChangeMe123!",
                email      = None,
                is_admin   = True,
                created_by = "system",
            )
            print("[AUTH] First admin created  username=admin  password=ChangeMe123!")
            print("[AUTH] ⚠  Change this password immediately via /admin")
    finally:
        db.close()


@app.on_event("shutdown")
async def shutdown_event():
    get_scheduler().shutdown(wait=False)
    print("[APP] Scheduler shut down")


# ── Routes ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    jobs      = get_all_active_jobs()
    companies = get_all_companies()
    return templates.TemplateResponse("index.html", {
        "request":   request,
        "jobs":      jobs,
        "companies": companies,
    })


@app.get("/add", response_class=HTMLResponse)
async def add_form(request: Request):
    sites_au  = [s for s in SITES if s["geo"] == "au"]
    sites_nz  = [s for s in SITES if s["geo"] == "nz"]
    companies = get_all_companies()
    return templates.TemplateResponse("add.html", {
        "request":   request,
        "sites_au":  sites_au,
        "sites_nz":  sites_nz,
        "companies": companies,
    })


@app.post("/add")
async def add_submit(
    request: Request,
    product_name: str = Form(...),
    target_price: float = Form(...),
    user_email: str = Form(...),
    schedule_interval: str = Form(...),
    company_id: str = Form(...),
):
    form           = await request.form()
    selected_sites = form.getlist("selected_sites")
    companies      = get_all_companies()

    def _err(msg: str):
        return templates.TemplateResponse("add.html", {
            "request":   request,
            "sites_au":  [s for s in SITES if s["geo"] == "au"],
            "sites_nz":  [s for s in SITES if s["geo"] == "nz"],
            "companies": companies,
            "error":     msg,
        }, status_code=400)

    if not selected_sites:
        return _err("Please select at least one site.")
    if not company_id:
        return _err("Please select a company.")

    _creator = getattr(request.state, "username", "unknown")

    job = create_job({
        "job_type":             "price_watch",
        "product_name":         product_name,
        "target_price":         target_price,
        "user_email":           user_email,
        "schedule_interval":    schedule_interval,
        "selected_sites":       selected_sites,
        "created_by_username":  _creator,
        "company_id":           company_id,
    })

    if job:
        register_job(job)
        log_activity(
            username   = _creator,
            event_type = "job_created",
            detail     = f"Price watch: {product_name} (target ${target_price})",
            ip_address = request.headers.get("x-real-ip") or request.headers.get("cf-connecting-ip") or (request.client.host if request.client else None),
            job_id     = job.id,
        )

    return RedirectResponse(url="/", status_code=303)


@app.get("/add-scout", response_class=HTMLResponse)
async def add_scout_form(request: Request):
    sites_au  = [s for s in SITES if s["geo"] == "au"]
    sites_nz  = [s for s in SITES if s["geo"] == "nz"]
    companies = get_all_companies()
    return templates.TemplateResponse("add_scout.html", {
        "request":   request,
        "sites_au":  sites_au,
        "sites_nz":  sites_nz,
        "companies": companies,
    })


@app.post("/add-scout")
async def add_scout_submit(
    request: Request,
    product_name: str = Form(...),
    user_email: str = Form(...),
    schedule_interval: str = Form(...),
    company_id: str = Form(...),
):
    form           = await request.form()
    selected_sites = form.getlist("selected_sites")
    companies      = get_all_companies()

    def _err(msg: str):
        return templates.TemplateResponse("add_scout.html", {
            "request":   request,
            "sites_au":  [s for s in SITES if s["geo"] == "au"],
            "sites_nz":  [s for s in SITES if s["geo"] == "nz"],
            "companies": companies,
            "error":     msg,
        }, status_code=400)

    if not selected_sites:
        return _err("Please select at least one site.")
    if not company_id:
        return _err("Please select a company.")

    _creator = getattr(request.state, "username", "unknown")

    job = create_job({
        "job_type":            "availability_scout",
        "product_name":        product_name,
        "target_price":        None,
        "user_email":          user_email,
        "schedule_interval":   schedule_interval,
        "selected_sites":      selected_sites,
        "created_by_username": _creator,
        "company_id":          company_id,
    })

    if job:
        register_job(job)
        log_activity(
            username   = _creator,
            event_type = "job_created",
            detail     = f"Availability scout: {product_name}",
            ip_address = request.headers.get("x-real-ip") or request.headers.get("cf-connecting-ip") or (request.client.host if request.client else None),
            job_id     = job.id,
        )

    return RedirectResponse(url="/", status_code=303)


@app.get("/job/{job_id}", response_class=HTMLResponse)
async def job_detail(request: Request, job_id: int):
    job = get_job_by_id(job_id)
    if not job or not job.is_active:
        return RedirectResponse(url="/", status_code=302)
    runs = get_runs_for_job(job_id, limit=50)
    return templates.TemplateResponse("detail.html", {
        "request": request,
        "job":     job,
        "runs":    runs,
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
                "job_id":            job_id,
                "run_result_id":     run.id,
                "email_to":          job.user_email,
                "sites_below_target": result.get("available_sites", []),
                "lowest_price_found": result.get("lowest_price") or 0,
                "send_status":       "sent" if success else "failed",
            })
            alert_triggered = success
        else:
            if result["should_alert"] and not job.alert_sent:
                success = await send_alert_email(job, result["below_target"])
                create_alert_log({
                    "job_id":            job_id,
                    "run_result_id":     run.id,
                    "email_to":          job.user_email,
                    "sites_below_target": result["below_target"],
                    "lowest_price_found": result["lowest_price"] or 0,
                    "send_status":       "sent" if success else "failed",
                })
                update_alert_sent(job_id, True)
                alert_triggered = True
            elif not result["should_alert"] and job.alert_sent:
                update_alert_sent(job_id, False)

    complete_run(run.id, {
        "results":       result.get("results", []),
        "sites_checked": result.get("sites_checked", []),
        "lowest_price":  result.get("lowest_price"),
        "lowest_site":   result.get("lowest_site"),
        "alert_triggered": alert_triggered,
        "error_sites":   result.get("error_sites", []),
    })

    next_run = _get_next_run_time(job.schedule_interval if job else "24h")
    update_last_run(job_id, result.get("lowest_price"), next_run)

    log_activity(
        username   = "system",
        event_type = "job_run_now",
        detail     = f"Manual run triggered for job #{job_id}",
        job_id     = job_id,
    )

    return JSONResponse({"run_id": run.id, "job_id": job_id})


@app.get("/job/{job_id}/edit", response_class=HTMLResponse)
async def edit_form(request: Request, job_id: int):
    job = get_job_by_id(job_id)
    if not job or not job.is_active:
        return RedirectResponse(url="/", status_code=302)
    sites_au = [s for s in SITES if s["geo"] == "au"]
    sites_nz = [s for s in SITES if s["geo"] == "nz"]
    return templates.TemplateResponse("edit.html", {
        "request":  request,
        "job":      job,
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
    form           = await request.form()
    selected_sites = form.getlist("selected_sites")

    update_job(job_id, {
        "product_name":      product_name,
        "target_price":      target_price,
        "user_email":        user_email,
        "schedule_interval": schedule_interval,
        "selected_sites":    selected_sites,
    })

    cancel_job(job_id)
    job = get_job_by_id(job_id)
    if job:
        register_job(job)

    log_activity(
        username   = getattr(request.state, "username", "unknown"),
        event_type = "job_edited",
        detail     = f"Edited job: {product_name}",
        ip_address = request.headers.get("x-real-ip") or request.headers.get("cf-connecting-ip") or (request.client.host if request.client else None),
        job_id     = job_id,
    )
    return RedirectResponse(url=f"/job/{job_id}", status_code=303)


@app.post("/job/{job_id}/delete")
async def delete_job(job_id: int, request: Request):
    _job   = get_job_by_id(job_id)
    _name  = _job.product_name if _job else f"#{job_id}"
    _actor = getattr(request.state, "username", "unknown")
    soft_delete_job(job_id)
    cancel_job(job_id)
    log_activity(
        username   = _actor,
        event_type = "job_deleted",
        detail     = f"Deleted job: {_name}",
        ip_address = request.headers.get("x-real-ip") or request.headers.get("cf-connecting-ip") or (request.client.host if request.client else None),
        job_id     = job_id,
    )
    return RedirectResponse(url="/", status_code=303)


@app.get("/health")
async def health():
    scheduler = get_scheduler()
    return JSONResponse({
        "status":             "ok",
        "scheduler_running":  scheduler.running,
    })


# ── Companies ──────────────────────────────────────────────────────────────

@app.get("/companies", response_class=HTMLResponse)
async def companies_page(request: Request):
    data = get_companies_with_active_jobs()
    return templates.TemplateResponse("companies.html", {
        "request":      request,
        "company_data": data,
    })


@app.post("/api/companies")
async def api_create_company(request: Request):
    """JSON endpoint — body: {name: str} → {id, name} | {error: str}"""
    try:
        body = await request.json()
        name = (body.get("name") or "").strip()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    if not name:
        return JSONResponse({"error": "Name is required"}, status_code=400)
    company, err = create_company(name)
    if err and not company:
        return JSONResponse({"error": err}, status_code=409)
    return JSONResponse({"id": company.id, "name": company.name})


@app.post("/companies/{company_id}/delete")
async def delete_company_route(request: Request, company_id: int):
    ok, msg = delete_company(company_id)
    if not ok:
        data = get_companies_with_active_jobs()
        return templates.TemplateResponse("companies.html", {
            "request":      request,
            "company_data": data,
            "error":        msg,
        }, status_code=400)
    return RedirectResponse(url="/companies", status_code=303)


# ── Site Testing ─────────────────────────────────────────────────────────────

@app.get("/site-test", response_class=HTMLResponse)
async def site_test_page(request: Request):
    """Configuration page: pick sites, set per-site test product, threshold."""
    recent_runs = get_recent_site_test_runs(limit=10)
    return templates.TemplateResponse("site_test.html", {
        "request":     request,
        "sites":       SITES,
        "default_product": DEFAULT_TEST_PRODUCT,
        "recent_runs": recent_runs,
    })


async def _execute_site_test(run_id: int, site_products: dict, threshold: float,
                              geo_filter: Optional[str], tier_filter: Optional[str],
                              selected_domains: Optional[list], concurrency: int, timeout: int):
    """Background task — runs the test suite and persists progress + final results."""
    async def on_progress(results_so_far):
        update_site_test_progress(run_id, results_so_far, len(results_so_far))

    try:
        results = await run_site_tests(
            site_products=site_products,
            threshold=threshold,
            geo_filter=geo_filter,
            tier_filter=tier_filter,
            selected_domains=selected_domains,
            concurrency=concurrency,
            timeout=timeout,
            on_progress=on_progress,
        )
        complete_site_test_run(run_id, results, status="completed")
    except Exception as e:
        print(f"[SITE TEST] run {run_id} failed: {e}")
        complete_site_test_run(run_id, [], status="failed")


@app.post("/site-test/run")
async def site_test_start(request: Request, background_tasks: BackgroundTasks):
    """Starts a test run in the background, returns immediately with run_id."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    site_products    = body.get("site_products", {})   # {domain: product_name}
    threshold        = float(body.get("threshold", 50.0))
    geo_filter       = body.get("geo_filter") or None
    tier_filter      = body.get("tier_filter") or None
    selected_domains = body.get("selected_domains") or None
    concurrency      = int(body.get("concurrency", 3))
    timeout          = int(body.get("timeout", 90))

    sites = select_sites(geo_filter, tier_filter, selected_domains)
    if not sites:
        return JSONResponse({"error": "No sites match the selected filters."}, status_code=400)

    _creator = getattr(request.state, "username", "unknown")

    run = create_site_test_run({
        "threshold":     threshold,
        "site_products": site_products,
        "geo_filter":    geo_filter,
        "tier_filter":   tier_filter,
        "total_sites":   len(sites),
        "started_by":    _creator,
    })
    if not run:
        return JSONResponse({"error": "Could not create test run."}, status_code=500)

    background_tasks.add_task(
        _execute_site_test, run.id, site_products, threshold,
        geo_filter, tier_filter, selected_domains, concurrency, timeout,
    )

    log_activity(
        username   = _creator,
        event_type = "site_test_started",
        detail     = f"Site test #{run.id}: {len(sites)} sites, threshold {threshold}",
    )

    return JSONResponse({"run_id": run.id, "total_sites": len(sites)})


@app.get("/api/site-test/status/{run_id}")
async def site_test_status(run_id: int):
    """Polled by the results page while a run is in progress."""
    run = get_site_test_run(run_id)
    if not run:
        return JSONResponse({"error": "Run not found"}, status_code=404)
    results = _from_json(run.results_json)
    return JSONResponse({
        "run_id":          run.id,
        "status":          run.status,
        "total_sites":     run.total_sites,
        "completed_count": run.completed_count,
        "results":         results,
    })


@app.get("/site-test/results/{run_id}", response_class=HTMLResponse)
async def site_test_results_page(request: Request, run_id: int):
    run = get_site_test_run(run_id)
    if not run:
        return RedirectResponse(url="/site-test", status_code=302)
    results = _from_json(run.results_json)
    summary = summarize(results) if results else {
        "ok": 0, "parse_ok_no_match": 0, "fetch_fail": 0,
        "parse_fail": 0, "skipped": 0, "total": run.total_sites, "total_elapsed": 0,
    }
    return templates.TemplateResponse("site_test_results.html", {
        "request": request,
        "run":     run,
        "results": sorted(results, key=lambda r: (r["verdict"] != "OK", r["domain"])),
        "summary": summary,
    })


@app.get("/site-test/results/{run_id}/pdf")
async def site_test_results_pdf(run_id: int):
    run = get_site_test_run(run_id)
    if not run:
        return JSONResponse({"error": "Run not found"}, status_code=404)
    results = _from_json(run.results_json)
    summary = summarize(results)
    pdf_buffer = generate_pdf_report(run, results, summary)
    filename = f"site-test-report-{run.id}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
