import json
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session, sessionmaker

from db.models import AlertLog, Base, RunResult, WatchlistJob, engine

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    return SessionLocal()


def get_all_active_jobs() -> list[WatchlistJob]:
    db = get_db()
    try:
        return (
            db.query(WatchlistJob)
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
        return db.query(WatchlistJob).filter(WatchlistJob.id == job_id).first()
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
        raw_price = data.get("target_price")
        job = WatchlistJob(
            job_type=data.get("job_type", "price_watch"),
            product_name=data["product_name"],
            target_price=float(raw_price) if raw_price is not None else None,
            user_email=data["user_email"],
            schedule_interval=data["schedule_interval"],
            selected_sites=selected,
            alert_sent=False,
            is_active=True,
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
            job_id=job_id,
            run_type=run_type,
            started_at=datetime.utcnow(),
            sites_checked="[]",
            results_json="[]",
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
        run.completed_at = datetime.utcnow()
        results = data.get("results", [])
        run.results_json = json.dumps(results) if isinstance(results, list) else results
        sites = data.get("sites_checked", [])
        run.sites_checked = json.dumps(sites) if isinstance(sites, list) else sites
        run.lowest_price = data.get("lowest_price")
        run.lowest_site = data.get("lowest_site")
        run.alert_triggered = data.get("alert_triggered", False)
        error_sites = data.get("error_sites", [])
        run.error_sites = json.dumps(error_sites) if isinstance(error_sites, list) else error_sites
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
            job_id=data["job_id"],
            run_result_id=data["run_result_id"],
            email_to=data["email_to"],
            sites_below_target=json.dumps(sites) if isinstance(sites, list) else sites,
            lowest_price_found=data["lowest_price_found"],
            send_status=data.get("send_status", "sent"),
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
            job.last_run_at = datetime.utcnow()
            job.last_lowest_price = lowest
            job.next_run_at = next_run
            db.commit()
    except Exception as e:
        print(f"[DB ERROR] update_last_run({job_id}): {e}")
        db.rollback()
    finally:
        db.close()
