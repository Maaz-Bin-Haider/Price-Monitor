# analytics.py
# Place at: /app/analytics.py  (same level as main.py)
#
# All DB query helpers used by the analytics router.
# Pure synchronous SQLAlchemy — same style as the rest of the project.

import json
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

from db.models import SessionLocal, WatchlistJob, RunResult, AlertLog
from analytics_models import ActivityLog


# ── Activity logging ───────────────────────────────────────────────────────────

def log_activity(
    username:    str,
    event_type:  str,
    detail:      str            = "",
    ip_address:  Optional[str]  = None,
    job_id:      Optional[int]  = None,
    target_user: Optional[str]  = None,
) -> None:
    """
    Write one activity row. Call this from any route handler.
    Opens and closes its own session so callers don't need to worry about it.
    Never raises — a logging failure must not break the main action.
    """
    try:
        db = SessionLocal()
        try:
            db.add(ActivityLog(
                username    = username,
                event_type  = event_type,
                detail      = detail,
                ip_address  = ip_address,
                job_id      = job_id,
                target_user = target_user,
            ))
            db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"[ANALYTICS] Failed to log activity: {e}")


# ── Products analytics ─────────────────────────────────────────────────────────

def get_all_jobs_for_analytics(db: Session) -> list:
    """All jobs (active + deleted) with run counts and last run info."""
    return (
        db.query(WatchlistJob)
        .order_by(WatchlistJob.created_at.desc())
        .all()
    )


def get_active_jobs_for_analytics(db: Session) -> list:
    return (
        db.query(WatchlistJob)
        .filter(WatchlistJob.is_active == True)
        .order_by(WatchlistJob.created_at.desc())
        .all()
    )


def get_job_analytics_detail(db: Session, job_id: int) -> Optional[WatchlistJob]:
    return db.query(WatchlistJob).filter_by(id=job_id).first()


def get_runs_for_job_analytics(db: Session, job_id: int, limit: int = 100) -> list:
    return (
        db.query(RunResult)
        .filter_by(job_id=job_id)
        .order_by(RunResult.started_at.desc())
        .limit(limit)
        .all()
    )


def get_alerts_for_job(db: Session, job_id: int) -> list:
    return (
        db.query(AlertLog)
        .filter_by(job_id=job_id)
        .order_by(AlertLog.sent_at.desc())
        .all()
    )


def get_price_trend(db: Session, job_id: int) -> list:
    """Returns [{date, lowest_price}] for charting price over time."""
    runs = (
        db.query(RunResult)
        .filter(RunResult.job_id == job_id, RunResult.lowest_price != None)
        .order_by(RunResult.started_at.asc())
        .all()
    )
    return [
        {
            "date":  r.started_at.strftime("%Y-%m-%d %H:%M"),
            "price": r.lowest_price,
            "site":  r.lowest_site or "",
        }
        for r in runs
    ]


# ── Site performance analytics ─────────────────────────────────────────────────

def get_site_performance(db: Session) -> list:
    """
    For every domain that has appeared in run results, compute:
      - total times checked
      - times it had results (lowest_site matched)
      - times it was in error_sites
    Returns list sorted by fail rate descending.
    """
    runs = db.query(RunResult).all()
    stats: dict = {}

    for run in runs:
        sites_checked = _safe_json(run.sites_checked)
        error_sites   = _safe_json(run.error_sites)

        for domain in sites_checked:
            if domain not in stats:
                stats[domain] = {"checked": 0, "errors": 0, "found_lowest": 0}
            stats[domain]["checked"] += 1
            if domain in error_sites:
                stats[domain]["errors"] += 1
            if run.lowest_site and domain in run.lowest_site:
                stats[domain]["found_lowest"] += 1

    result = []
    for domain, s in stats.items():
        checked = s["checked"] or 1
        result.append({
            "domain":       domain,
            "checked":      s["checked"],
            "errors":       s["errors"],
            "found_lowest": s["found_lowest"],
            "error_rate":   round(s["errors"] / checked * 100, 1),
            "success_rate": round((checked - s["errors"]) / checked * 100, 1),
        })

    return sorted(result, key=lambda x: x["error_rate"], reverse=True)


# ── Alert analytics ────────────────────────────────────────────────────────────

def get_alert_stats(db: Session) -> dict:
    total_runs   = db.query(RunResult).count()
    total_alerts = db.query(AlertLog).count()
    sent_alerts  = db.query(AlertLog).filter_by(send_status="sent").count()
    failed_alerts = db.query(AlertLog).filter_by(send_status="failed").count()

    return {
        "total_runs":     total_runs,
        "total_alerts":   total_alerts,
        "sent_alerts":    sent_alerts,
        "failed_alerts":  failed_alerts,
        "alert_rate":     round(total_alerts / total_runs * 100, 1) if total_runs else 0,
    }


# ── User activity ──────────────────────────────────────────────────────────────

def get_activity_for_user(db: Session, username: str, limit: int = 200) -> list:
    return (
        db.query(ActivityLog)
        .filter(ActivityLog.username == username)
        .order_by(ActivityLog.timestamp.desc())
        .limit(limit)
        .all()
    )


def get_all_recent_activity(db: Session, limit: int = 200) -> list:
    return (
        db.query(ActivityLog)
        .order_by(ActivityLog.timestamp.desc())
        .limit(limit)
        .all()
    )


def get_activity_summary_per_user(db: Session) -> list:
    """Returns per-user event counts for the summary table."""
    from auth_models import AuthUser
    users = db.query(AuthUser).order_by(AuthUser.created_at.desc()).all()
    result = []
    for user in users:
        logs = (
            db.query(ActivityLog)
            .filter(ActivityLog.username == user.username)
            .all()
        )
        logins   = sum(1 for l in logs if l.event_type == "login")
        jobs_add = sum(1 for l in logs if l.event_type == "job_created")
        last_act = max((l.timestamp for l in logs), default=None)
        result.append({
            "username":    user.username,
            "is_admin":    user.is_admin,
            "is_active":   user.is_active,
            "total_events": len(logs),
            "logins":      logins,
            "jobs_added":  jobs_add,
            "last_active": last_act.strftime("%Y-%m-%d %H:%M") if last_act else "Never",
        })
    return result


# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe_json(val) -> list:
    if isinstance(val, list):
        return val
    try:
        return json.loads(val) if val else []
    except Exception:
        return []
