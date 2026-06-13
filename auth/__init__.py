# auth/__init__.py — public API for the auth package
from auth.core import (
    hash_password, verify_password,
    create_access_token, decode_token,
    is_ip_locked, record_failed_attempt, clear_failed_attempts, unlock_ip,
    get_user, authenticate_user, create_user, list_users,
    toggle_user_active, delete_user_by_id, list_locked_ips,
    COOKIE_NAME, TOKEN_EXPIRE, MAX_ATTEMPTS, LOCKOUT_HOURS,
)
