# auth.py
# Place this file at: /app/auth.py  (same level as main.py)
#
# All DB calls are SYNCHRONOUS — matches your project's existing style
# (SessionLocal, not AsyncSession).

import os
from datetime import datetime, timedelta
from typing import Optional, Tuple

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from auth_models import AuthUser, AuthLoginAttempt

# ── Config (values come from .env) ────────────────────────────────────────────
SECRET_KEY    = os.getenv("AUTH_SECRET_KEY", "CHANGE_ME")
ALGORITHM     = "HS256"
TOKEN_EXPIRE  = int(os.getenv("AUTH_TOKEN_EXPIRE_MINUTES", "480"))  # 8 hours
COOKIE_NAME   = "pm_session"

MAX_ATTEMPTS  = 5    # failed logins before lockout
LOCKOUT_HOURS = 2    # hours the IP stays locked

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Password helpers ───────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)


# ── JWT helpers ────────────────────────────────────────────────────────────────

def create_access_token(username: str, is_admin: bool) -> str:
    expire  = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE)
    payload = {"sub": username, "admin": is_admin, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> Optional[dict]:
    """Returns payload dict or None if invalid / expired."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


# ── Brute-force protection ─────────────────────────────────────────────────────

def is_ip_locked(db: Session, ip: str) -> bool:
    row = db.query(AuthLoginAttempt).filter_by(ip_address=ip).first()
    if row is None:
        return False
    if row.locked_until and row.locked_until > datetime.utcnow():
        return True
    return False

def record_failed_attempt(db: Session, ip: str) -> int:
    """
    Increments the counter for this IP.
    Locks the IP for LOCKOUT_HOURS once MAX_ATTEMPTS is reached.
    Returns the new attempt count.
    """
    now = datetime.utcnow()
    row = db.query(AuthLoginAttempt).filter_by(ip_address=ip).first()
    if row is None:
        row = AuthLoginAttempt(ip_address=ip, attempt_count=1, last_attempt=now)
        db.add(row)
    else:
        row.attempt_count += 1
        row.last_attempt   = now

    if row.attempt_count >= MAX_ATTEMPTS:
        row.locked_until = now + timedelta(hours=LOCKOUT_HOURS)

    db.commit()
    return row.attempt_count

def clear_failed_attempts(db: Session, ip: str) -> None:
    """Called after a successful login — resets the counter."""
    row = db.query(AuthLoginAttempt).filter_by(ip_address=ip).first()
    if row:
        row.attempt_count = 0
        row.locked_until  = None
        db.commit()

def unlock_ip(db: Session, ip: str) -> None:
    """Admin manually unlocks a blocked IP."""
    row = db.query(AuthLoginAttempt).filter_by(ip_address=ip).first()
    if row:
        row.attempt_count = 0
        row.locked_until  = None
        db.commit()


# ── User DB helpers ────────────────────────────────────────────────────────────

def get_user(db: Session, username: str) -> Optional[AuthUser]:
    return db.query(AuthUser).filter_by(username=username, is_active=True).first()

def authenticate_user(db: Session, ip: str, username: str, password: str) -> Tuple[Optional[AuthUser], str]:
    """
    Returns (user, error_message).
    error_message is empty string ("") on success.
    """
    if is_ip_locked(db, ip):
        return None, f"Too many failed attempts. Your IP is blocked for {LOCKOUT_HOURS} hours."

    user = get_user(db, username)
    if user is None or not verify_password(password, user.hashed_pw):
        count     = record_failed_attempt(db, ip)
        remaining = MAX_ATTEMPTS - count
        if remaining <= 0:
            return None, f"Too many failed attempts. Your IP is blocked for {LOCKOUT_HOURS} hours."
        return None, f"Invalid username or password. {remaining} attempt(s) remaining before lockout."

    clear_failed_attempts(db, ip)
    return user, ""

def create_user(db: Session, username: str, password: str,
                email: Optional[str], is_admin: bool, created_by: str) -> AuthUser:
    user = AuthUser(
        username   = username,
        email      = email or None,
        hashed_pw  = hash_password(password),
        is_admin   = is_admin,
        created_by = created_by,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def list_users(db: Session):
    return db.query(AuthUser).order_by(AuthUser.created_at.desc()).all()

def toggle_user_active(db: Session, user_id: int) -> Optional[AuthUser]:
    user = db.query(AuthUser).filter_by(id=user_id).first()
    if user:
        user.is_active = not user.is_active
        db.commit()
        db.refresh(user)
    return user

def delete_user_by_id(db: Session, user_id: int) -> bool:
    user = db.query(AuthUser).filter_by(id=user_id).first()
    if user:
        db.delete(user)
        db.commit()
        return True
    return False

def list_locked_ips(db: Session):
    now = datetime.utcnow()
    return db.query(AuthLoginAttempt).filter(
        AuthLoginAttempt.locked_until > now
    ).all()
