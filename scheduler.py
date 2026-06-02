import json
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import settings
from db.crud import (
    complete_run,
    create_alert_log,
    create_run,
    get_job_by_id,
    get_scheduled_jobs,
    update_alert_sent,
    update_last_run,
)
from notifications.email import send_alert_email, send_availability_email
from scraper.runner import run_search, run_availability_search

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    """Return the module-level scheduler singleton."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


def build_trigger(interval: str):
    """Map schedule_interval string to APScheduler trigger."""
    if interval == "12h":
        return IntervalTrigger(hours=12)
    elif interval == "24h":
        return IntervalTrigger(hours=24)
    elif interval == "weekly":
        return CronTrigger(
            day_of_week="mon",
            hour=settings.SCHEDULE_DEFAULT_HOUR,
            minute=0,
        )
    elif interval == "monthly":
        return CronTrigger(
            day=1,
            hour=settings.SCHEDULE_DEFAULT_HOUR,
            minute=0,
        )
    else:
        # Default to daily
        return IntervalTrigger(hours=24)


def _get_next_run_time(interval: str) -> datetime:
    """Calculate next expected run time for display."""
    now = datetime.utcnow()
    if interval == "12h":
        return now + timedelta(hours=12)
    elif interval == "24h":
        return now + timedelta(hours=24)
    elif interval == "weekly":
        # Next Monday at default hour
        days_ahead = 7 - now.weekday()
        if days_ahead == 7:
            days_ahead = 0
        next_monday = now + timedelta(days=days_ahead)
        return next_monday.replace(hour=settings.SCHEDULE_DEFAULT_HOUR, minute=0, second=0)
    elif interval == "monthly":
        # 1st of next month
        if now.month == 12:
            return now.replace(year=now.year + 1, month=1, day=1, hour=settings.SCHEDULE_DEFAULT_HOUR, minute=0)
        return now.replace(month=now.month + 1, day=1, hour=settings.SCHEDULE_DEFAULT_HOUR, minute=0)
    return now + timedelta(hours=24)


def register_job(job) -> None:
    """Register or replace a watchlist job in APScheduler."""
    scheduler = get_scheduler()
    trigger = build_trigger(job.schedule_interval)
    try:
        scheduler.add_job(
            run_scheduled_job,
            trigger=trigger,
            args=[job.id],
            id=f"job_{job.id}",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        print(f"[SCHEDULER] Registered job_{job.id} ({job.product_name})")
    except Exception as e:
        print(f"[SCHEDULER] Failed to register job_{job.id}: {e}")


def cancel_job(job_id: int) -> None:
    """Remove a job from APScheduler. Silent if not found."""
    scheduler = get_scheduler()
    try:
        scheduler.remove_job(f"job_{job_id}")
        print(f"[SCHEDULER] Cancelled job_{job_id}")
    except Exception:
        pass  # Job not found — silent


async def run_scheduled_job(job_id: int) -> None:
    """Core scheduled job runner. Also called for instant runs separately."""
    job = get_job_by_id(job_id)
    if not job or not job.is_active:
        return

    selected_sites = json.loads(job.selected_sites) if isinstance(job.selected_sites, str) else job.selected_sites

    job_type = getattr(job, "job_type", "price_watch") or "price_watch"

    run = create_run(job_id, "scheduled")
    if not run:
        return

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
        print(f"[SCHEDULER] run_search error for job_{job_id}: {e}")
        complete_run(run.id, {
            "results": [],
            "sites_checked": [],
            "lowest_price": None,
            "lowest_site": None,
            "alert_triggered": False,
            "error_sites": [],
        })
        return

    alert_triggered = False

    job = get_job_by_id(job_id)  # Refresh
    if job:
        if job_type == "availability_scout":
            # Always email the availability report
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
            # Price watch: original alert state machine
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


def restore_all_jobs() -> None:
    """Re-register all active watchlist jobs on startup."""
    jobs = get_scheduled_jobs()
    for job in jobs:
        try:
            register_job(job)
        except Exception as e:
            print(f"[SCHEDULER] Failed restoring job_{job.id}: {e}")
    print(f"[SCHEDULER] Restored {len(jobs)} jobs")
