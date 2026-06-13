# auth_models.py
# auth/models.py — SQLAlchemy models for the auth system
#
# Uses the SAME Base and engine from db/models.py so the tables land
# in your existing PostgreSQL database alongside watchlist_jobs etc.

from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from db.models import Base   # ← your existing Base


class AuthUser(Base):
    __tablename__ = "auth_users"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    username    = Column(String(64),  unique=True, nullable=False, index=True)
    email       = Column(String(255), unique=True, nullable=True)
    hashed_pw   = Column(Text,        nullable=False)
    is_admin    = Column(Boolean,     default=False, nullable=False)
    is_active   = Column(Boolean,     default=True,  nullable=False)
    created_at  = Column(DateTime,    default=datetime.utcnow)
    created_by  = Column(String(64),  nullable=True)   # username of admin who created this


class AuthLoginAttempt(Base):
    """
    Tracks failed login attempts per IP address.
    When attempt_count >= 5 the IP is blocked until locked_until.
    """
    __tablename__ = "auth_login_attempts"

    id            = Column(Integer,    primary_key=True, autoincrement=True)
    ip_address    = Column(String(45), unique=True, nullable=False, index=True)
    attempt_count = Column(Integer,    default=0,   nullable=False)
    locked_until  = Column(DateTime,   nullable=True)   # None = not locked
    last_attempt  = Column(DateTime,   nullable=True)
