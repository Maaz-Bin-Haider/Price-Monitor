import os
from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, create_engine
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker
from config import settings


class Base(DeclarativeBase):
    pass


# ── Company ────────────────────────────────────────────────────────────────
class Company(Base):
    __tablename__ = "companies"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(String(200), nullable=False, unique=True)  # stored as Title Case
    created_at = Column(DateTime, default=datetime.utcnow)

    jobs = relationship("WatchlistJob", back_populates="company")


# ── WatchlistJob ───────────────────────────────────────────────────────────
class WatchlistJob(Base):
    __tablename__ = "watchlist_jobs"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    job_type            = Column(String(20), nullable=False, default="price_watch")
    product_name        = Column(String(500), nullable=False)
    target_price        = Column(Float, nullable=True)
    user_email          = Column(String(320), nullable=False)
    schedule_interval   = Column(String(20), nullable=False)
    selected_sites      = Column(Text, nullable=False)
    alert_sent          = Column(Boolean, default=False)
    created_at          = Column(DateTime, default=datetime.utcnow)
    last_run_at         = Column(DateTime, nullable=True)
    next_run_at         = Column(DateTime, nullable=True)
    last_lowest_price   = Column(Float, nullable=True)
    is_active           = Column(Boolean, default=True)
    created_by_username = Column(String(64), nullable=True, default="unknown")
    # nullable — existing products keep working; new ones must provide one
    company_id          = Column(Integer, ForeignKey("companies.id"), nullable=True)

    company = relationship("Company", back_populates="jobs")
    runs    = relationship("RunResult", back_populates="job", cascade="all, delete-orphan")
    alerts  = relationship("AlertLog",  back_populates="job", cascade="all, delete-orphan")


# ── RunResult ──────────────────────────────────────────────────────────────
class RunResult(Base):
    __tablename__ = "run_results"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    job_id          = Column(Integer, ForeignKey("watchlist_jobs.id"), nullable=False)
    run_type        = Column(String(20), nullable=False)
    started_at      = Column(DateTime, nullable=False)
    completed_at    = Column(DateTime, nullable=True)
    sites_checked   = Column(Text, nullable=False)
    results_json    = Column(Text, nullable=False)
    lowest_price    = Column(Float, nullable=True)
    lowest_site     = Column(String(200), nullable=True)
    alert_triggered = Column(Boolean, default=False)
    error_sites     = Column(Text, nullable=True)

    job        = relationship("WatchlistJob", back_populates="runs")
    alert_logs = relationship("AlertLog", back_populates="run_result")


# ── AlertLog ───────────────────────────────────────────────────────────────
class AlertLog(Base):
    __tablename__ = "alert_log"

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    job_id             = Column(Integer, ForeignKey("watchlist_jobs.id"), nullable=False)
    run_result_id      = Column(Integer, ForeignKey("run_results.id"), nullable=False)
    sent_at            = Column(DateTime, default=datetime.utcnow)
    email_to           = Column(String(320), nullable=False)
    sites_below_target = Column(Text, nullable=False)
    lowest_price_found = Column(Float, nullable=False)
    send_status        = Column(String(20), default="sent")

    job        = relationship("WatchlistJob", back_populates="alerts")
    run_result = relationship("RunResult", back_populates="alert_logs")


# ── DB engine ──────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
