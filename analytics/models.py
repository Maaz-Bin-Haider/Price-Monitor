# analytics_models.py
# analytics/models.py — SQLAlchemy model for the activity_log table
#
# Adds the activity_log table to your existing PostgreSQL database.
# The created_by_username column on watchlist_jobs is handled via
# Base.metadata.create_all + ALTER TABLE in the startup migration script.

from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, Text
from db.models import Base


class ActivityLog(Base):
    """
    Persistent log of every user action in the system.

    event_type values:
        login           — user signed in
        logout          — user signed out
        login_failed    — wrong password attempt
        job_created     — new watchlist job added
        job_edited      — job settings changed
        job_deleted     — job soft-deleted
        job_run_now     — manual run triggered
        user_created    — admin created a new auth user
        user_deleted    — admin deleted an auth user
        user_toggled    — admin enabled/disabled a user
        ip_unlocked     — admin unlocked a blocked IP
    """
    __tablename__ = "activity_log"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    timestamp   = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    username    = Column(String(64),  nullable=False, index=True)  # who did the action
    event_type  = Column(String(32),  nullable=False, index=True)
    detail      = Column(Text,        nullable=True)   # human-readable description
    ip_address  = Column(String(45),  nullable=True)   # client IP at time of action
    job_id      = Column(Integer,     nullable=True)   # set when event relates to a job
    target_user = Column(String(64),  nullable=True)   # set when admin acts on another user
