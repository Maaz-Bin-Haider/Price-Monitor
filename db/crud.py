import json
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session, joinedload, sessionmaker

from db.models import AlertLog, Base, Company, RunResult, SiteTestRun, WatchlistJob, engine

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

DEFAULT_COMPANIES = [
    # ── Mobile & computing ─────────────────────────────────────────────────
    "Apple", "Samsung", "Google", "Microsoft", "Sony", "LG", "Motorola",
    "OnePlus", "Oppo", "Xiaomi", "Huawei", "Nokia", "Asus", "Lenovo",
    "HP", "Dell", "Acer", "CyberPower",
    # ── Audio ──────────────────────────────────────────────────────────────
    "Bose", "JBL", "Sennheiser", "Anker", "Beats", "Sonos",
    # ── Cameras & imaging ──────────────────────────────────────────────────
    "Canon", "Nikon", "Fujifilm", "Panasonic", "GoPro", "DJI",
    "Instax", "Kodak",
    # ── Gaming ─────────────────────────────────────────────────────────────
    "Nintendo", "Xbox", "Valve", "Razer", "Corsair", "SteelSeries", "HyperX",
    # ── Wearables ──────────────────────────────────────────────────────────
    "Garmin",
    # ── Home & peripherals ─────────────────────────────────────────────────
    "Philips", "Logitech", "Dyson", "Ninja", "Braun", "Fluke", "Starlink",
    # ── VR & smart glasses ─────────────────────────────────────────────────
    "Meta",
    # ── Speciality ─────────────────────────────────────────────────────────
    "Minelab",
]


def get_db() -> Session:
    return SessionLocal()


# ── Company CRUD ───────────────────────────────────────────────────────────

def _canonical(name: str) -> str:
    """Normalise to Title Case for storage and dedup comparisons."""
    return " ".join(w.capitalize() for w in name.strip().split())


def get_all_companies() -> list[Company]:
    db = get_db()
    try:
        return db.query(Company).order_by(Company.name).all()
    except Exception as e:
        print(f"[DB ERROR] get_all_companies: {e}")
        return []
    finally:
        db.close()


def get_company_by_name(name: str) -> Optional[Company]:
    canonical = _canonical(name)
    db = get_db()
    try:
        return db.query(Company).filter(Company.name.ilike(canonical)).first()
    except Exception as e:
        print(f"[DB ERROR] get_company_by_name: {e}")
        return None
    finally:
        db.close()


def create_company(name: str) -> tuple[Optional[Company], str]:
    """Returns (company, error). On duplicate returns existing company with a message."""
    canonical = _canonical(name)
    if not canonical:
        return None, "Company name cannot be empty."
    db = get_db()
    try:
        existing = db.query(Company).filter(Company.name.ilike(canonical)).first()
        if existing:
            return existing, f'"{existing.name}" already exists.'
        company = Company(name=canonical)
        db.add(company)
        db.commit()
        db.refresh(company)
        return company, ""
    except Exception as e:
        print(f"[DB ERROR] create_company: {e}")
        db.rollback()
        return None, "Failed to create company."
    finally:
        db.close()


def delete_company(company_id: int) -> tuple[bool, str]:
    """Blocked if any active products are assigned to this company."""
    db = get_db()
    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            return False, "Company not found."
        active_count = (
            db.query(WatchlistJob)
            .filter(WatchlistJob.company_id == company_id,
                    WatchlistJob.is_active == True)
            .count()
        )
        if active_count > 0:
            return False, (
                f'Cannot delete "{company.name}" — '
                f'it has {active_count} active product(s). Remove them first.'
            )
        db.delete(company)
        db.commit()
        return True, ""
    except Exception as e:
        print(f"[DB ERROR] delete_company({company_id}): {e}")
        db.rollback()
        return False, "Failed to delete company."
    finally:
        db.close()


def seed_default_companies() -> None:
    """Insert default companies that don't already exist. Idempotent."""
    db = get_db()
    try:
        for name in DEFAULT_COMPANIES:
            canonical = _canonical(name)
            exists = db.query(Company).filter(Company.name.ilike(canonical)).first()
            if not exists:
                db.add(Company(name=canonical))
        db.commit()
    except Exception as e:
        print(f"[DB ERROR] seed_default_companies: {e}")
        db.rollback()
    finally:
        db.close()


def get_companies_with_active_jobs() -> list[dict]:
    """Each entry: {company: Company, jobs: [WatchlistJob, ...]}"""
    db = get_db()
    try:
        companies = db.query(Company).order_by(Company.name).all()
        return [
            {"company": c, "jobs": [j for j in c.jobs if j.is_active]}
            for c in companies
        ]
    except Exception as e:
        print(f"[DB ERROR] get_companies_with_active_jobs: {e}")
        return []
    finally:
        db.close()


# ── WatchlistJob CRUD ──────────────────────────────────────────────────────

def get_all_active_jobs() -> list[WatchlistJob]:
    db = get_db()
    try:
        return (
            db.query(WatchlistJob)
            .options(joinedload(WatchlistJob.company))
            .filter(WatchlistJob.is_active == True)
            .order_by(WatchlistJob.created_at.desc())
            .all()
        )
    except Exception as e:
        print(f"[DB ERROR] get_all_active_jobs: {e}")
        return []
    finally:
        db.close()


def get_job_by_id(job_id: int) -> Optional[WatchlistJob]:
    db = get_db()
    try:
        return (
            db.query(WatchlistJob)
            .options(joinedload(WatchlistJob.company))
            .filter(WatchlistJob.id == job_id)
            .first()
        )
    except Exception as e:
        print(f"[DB ERROR] get_job_by_id({job_id}): {e}")
        return None
    finally:
        db.close()


def create_job(data: dict) -> Optional[WatchlistJob]:
    db = get_db()
    try:
        selected = data.get("selected_sites", [])
        if isinstance(selected, list):
            selected = json.dumps(selected)
        raw_price   = data.get("target_price")
        raw_company = data.get("company_id")
        job = WatchlistJob(
            job_type            = data.get("job_type", "price_watch"),
            product_name        = data["product_name"],
            target_price        = float(raw_price) if raw_price is not None else None,
            user_email          = data["user_email"],
            schedule_interval   = data["schedule_interval"],
            selected_sites      = selected,
            alert_sent          = False,
            is_active           = True,
            created_by_username = data.get("created_by_username", "unknown"),
            company_id          = int(raw_company) if raw_company else None,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job
    except Exception as e:
        print(f"[DB ERROR] create_job: {e}")
        db.rollback()
        return None
    finally:
        db.close()


def update_job(job_id: int, data: dict) -> Optional[WatchlistJob]:
    db = get_db()
    try:
        job = db.query(WatchlistJob).filter(WatchlistJob.id == job_id).first()
        if not job:
            return None
        for key, value in data.items():
            if key == "selected_sites" and isinstance(value, list):
                value = json.dumps(value)
            if hasattr(job, key):
                setattr(job, key, value)
        db.commit()
        db.refresh(job)
        return job
    except Exception as e:
        print(f"[DB ERROR] update_job({job_id}): {e}")
        db.rollback()
        return None
    finally:
        db.close()


def soft_delete_job(job_id: int) -> None:
    db = get_db()
    try:
        job = db.query(WatchlistJob).filter(WatchlistJob.id == job_id).first()
        if job:
            job.is_active = False
            db.commit()
    except Exception as e:
        print(f"[DB ERROR] soft_delete_job({job_id}): {e}")
        db.rollback()
    finally:
        db.close()


def get_runs_for_job(job_id: int, limit: int = 50) -> list[RunResult]:
    db = get_db()
    try:
        return (
            db.query(RunResult)
            .filter(RunResult.job_id == job_id)
            .order_by(RunResult.started_at.desc())
            .limit(limit)
            .all()
        )
    except Exception as e:
        print(f"[DB ERROR] get_runs_for_job({job_id}): {e}")
        return []
    finally:
        db.close()


def create_run(job_id: int, run_type: str) -> Optional[RunResult]:
    db = get_db()
    try:
        run = RunResult(
            job_id      = job_id,
            run_type    = run_type,
            started_at  = datetime.utcnow(),
            sites_checked = "[]",
            results_json  = "[]",
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run
    except Exception as e:
        print(f"[DB ERROR] create_run({job_id}): {e}")
        db.rollback()
        return None
    finally:
        db.close()


def complete_run(run_id: int, data: dict) -> None:
    db = get_db()
    try:
        run = db.query(RunResult).filter(RunResult.id == run_id).first()
        if not run:
            return
        run.completed_at  = datetime.utcnow()
        results           = data.get("results", [])
        run.results_json  = json.dumps(results) if isinstance(results, list) else results
        sites             = data.get("sites_checked", [])
        run.sites_checked = json.dumps(sites) if isinstance(sites, list) else sites
        run.lowest_price  = data.get("lowest_price")
        run.lowest_site   = data.get("lowest_site")
        run.alert_triggered = data.get("alert_triggered", False)
        error_sites       = data.get("error_sites", [])
        run.error_sites   = json.dumps(error_sites) if isinstance(error_sites, list) else error_sites
        db.commit()
    except Exception as e:
        print(f"[DB ERROR] complete_run({run_id}): {e}")
        db.rollback()
    finally:
        db.close()


def get_scheduled_jobs() -> list[WatchlistJob]:
    return get_all_active_jobs()


def create_alert_log(data: dict) -> Optional[AlertLog]:
    db = get_db()
    try:
        sites = data.get("sites_below_target", [])
        alert = AlertLog(
            job_id             = data["job_id"],
            run_result_id      = data["run_result_id"],
            email_to           = data["email_to"],
            sites_below_target = json.dumps(sites) if isinstance(sites, list) else sites,
            lowest_price_found = data["lowest_price_found"],
            send_status        = data.get("send_status", "sent"),
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        return alert
    except Exception as e:
        print(f"[DB ERROR] create_alert_log: {e}")
        db.rollback()
        return None
    finally:
        db.close()


def update_alert_sent(job_id: int, value: bool) -> None:
    db = get_db()
    try:
        job = db.query(WatchlistJob).filter(WatchlistJob.id == job_id).first()
        if job:
            job.alert_sent = value
            db.commit()
    except Exception as e:
        print(f"[DB ERROR] update_alert_sent({job_id}): {e}")
        db.rollback()
    finally:
        db.close()


def update_last_run(job_id: int, lowest: Optional[float], next_run: datetime) -> None:
    db = get_db()
    try:
        job = db.query(WatchlistJob).filter(WatchlistJob.id == job_id).first()
        if job:
            job.last_run_at       = datetime.utcnow()
            job.last_lowest_price = lowest
            job.next_run_at       = next_run
            db.commit()
    except Exception as e:
        print(f"[DB ERROR] update_last_run({job_id}): {e}")
        db.rollback()
    finally:
        db.close()


# ── SiteTestRun CRUD ───────────────────────────────────────────────────────

def create_site_test_run(data: dict) -> Optional[SiteTestRun]:
    db = get_db()
    try:
        site_products = data.get("site_products", {})
        run = SiteTestRun(
            status        = "running",
            threshold     = data.get("threshold", 50.0),
            site_products = json.dumps(site_products),
            geo_filter    = data.get("geo_filter"),
            tier_filter   = data.get("tier_filter"),
            results_json  = "[]",
            total_sites   = data.get("total_sites", 0),
            completed_count = 0,
            started_by    = data.get("started_by", "unknown"),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run
    except Exception as e:
        print(f"[DB ERROR] create_site_test_run: {e}")
        db.rollback()
        return None
    finally:
        db.close()


def get_site_test_run(run_id: int) -> Optional[SiteTestRun]:
    db = get_db()
    try:
        return db.query(SiteTestRun).filter(SiteTestRun.id == run_id).first()
    except Exception as e:
        print(f"[DB ERROR] get_site_test_run({run_id}): {e}")
        return None
    finally:
        db.close()


def get_recent_site_test_runs(limit: int = 20) -> list[SiteTestRun]:
    db = get_db()
    try:
        return (
            db.query(SiteTestRun)
            .order_by(SiteTestRun.started_at.desc())
            .limit(limit)
            .all()
        )
    except Exception as e:
        print(f"[DB ERROR] get_recent_site_test_runs: {e}")
        return []
    finally:
        db.close()


def update_site_test_progress(run_id: int, results: list, completed_count: int) -> None:
    """Called after each site finishes — updates progress for polling."""
    db = get_db()
    try:
        run = db.query(SiteTestRun).filter(SiteTestRun.id == run_id).first()
        if run:
            run.results_json     = json.dumps(results)
            run.completed_count  = completed_count
            db.commit()
    except Exception as e:
        print(f"[DB ERROR] update_site_test_progress({run_id}): {e}")
        db.rollback()
    finally:
        db.close()


def complete_site_test_run(run_id: int, results: list, status: str = "completed") -> None:
    db = get_db()
    try:
        run = db.query(SiteTestRun).filter(SiteTestRun.id == run_id).first()
        if run:
            run.results_json    = json.dumps(results)
            run.completed_count = len(results)
            run.status          = status
            run.completed_at    = datetime.utcnow()
            db.commit()
    except Exception as e:
        print(f"[DB ERROR] complete_site_test_run({run_id}): {e}")
        db.rollback()
    finally:
        db.close()
