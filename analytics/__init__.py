# analytics/__init__.py — public API for the analytics package
from analytics.queries import (
    log_activity,
    get_all_jobs_for_analytics, get_active_jobs_for_analytics,
    get_job_analytics_detail, get_runs_for_job_analytics,
    get_alerts_for_job, get_price_trend,
    get_site_performance, get_alert_stats,
    get_activity_for_user, get_all_recent_activity,
    get_activity_summary_per_user, _safe_json,
)
