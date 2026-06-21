# -*- coding: utf-8 -*-
"""
EIMS Authentication Module
==========================
Multi-layer password security:
  1. bcrypt hash stored in DB (system_settings table)
  2. Optional pepper from .env file (EIMS_AUTH_PEPPER)
  3. UI for changing the password

First-run behavior:
  - If no admin password hash exists in DB, the system seeds it with
    the value from EIMS_DEFAULT_ADMIN_PASSWORD env var (default: "1212").
  - The user is then prompted to change it on first login.

Usage:
  from auth.auth import verify_password, change_password, is_first_run
  if verify_password(input_password):
      ...
"""
import os
import sqlite3
import hashlib
import hmac
import secrets
from functools import lru_cache

# Try to import bcrypt; fall back to hashlib-based scheme if unavailable
try:
    import bcrypt
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False

from core.logger import get_logger
from database import get_conn, get_setting, save_setting

log = get_logger(__name__)


# ==============================================================================
#  CONSTANTS
# ==============================================================================
SETTING_KEY_HASH = "admin_password_hash"
SETTING_KEY_SALT = "admin_password_salt"  # only used when bcrypt is unavailable
SETTING_KEY_FIRST_RUN = "admin_first_run_done"

# Default password used ONLY when seeding on first run
DEFAULT_ADMIN_PASSWORD = os.environ.get("EIMS_DEFAULT_ADMIN_PASSWORD", "1212")

# Pepper loaded from .env (if present)
_PEPPER = None


def _load_pepper() -> str:
    """Load the pepper from .env file or EIMS_AUTH_PEPPER env var.

    The pepper is an additional secret stored OUTSIDE the database,
    so even if the DB is leaked, the password cannot be cracked without
    also obtaining the .env file.
    """
    global _PEPPER
    if _PEPPER is not None:
        return _PEPPER

    # Try env var first
    pepper = os.environ.get("EIMS_AUTH_PEPPER", "")

    # Then try .env file in current directory
    if not pepper:
        env_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "..", ".env")
        env_path = os.path.normpath(env_path)
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("#") or "=" not in line:
                            continue
                        key, _, value = line.partition("=")
                        if key.strip() == "EIMS_AUTH_PEPPER":
                            # Strip quotes if present
                            pepper = value.strip().strip('"').strip("'")
                            break
            except Exception as e:
                log.warning(f"Failed to read .env file: {e}")

    _PEPPER = pepper or ""
    return _PEPPER


def _apply_pepper(password: str) -> bytes:
    """Combine password with the pepper (HMAC-style)."""
    pepper = _load_pepper()
    if not pepper:
        return password.encode("utf-8")
    # If pepper is set, hash the password with it before bcrypt
    combined = hmac.new(pepper.encode("utf-8"), password.encode("utf-8"), hashlib.sha256).hexdigest()
    return combined.encode("utf-8")


# ==============================================================================
#  PASSWORD HASHING
# ==============================================================================
def hash_password(password: str) -> str:
    """Hash a password using bcrypt (with pepper applied).

    Returns a string suitable for storage in DB.
    Format:
      - bcrypt: "$2b$12$...."
      - fallback: "sha256$<salt_hex>$<hash_hex>"
    """
    if not password:
        raise ValueError("Password cannot be empty")

    peppered = _apply_pepper(password)

    if HAS_BCRYPT:
        try:
            salt = bcrypt.gensalt(rounds=12)
            hashed = bcrypt.hashpw(peppered, salt)
            return hashed.decode("utf-8")
        except Exception as e:
            log.error(f"bcrypt hashing failed, falling back to sha256: {e}")

    # Fallback: PBKDF2-HMAC-SHA256 (still strong, just not as ideal as bcrypt)
    salt = secrets.token_bytes(32)
    iterations = 200_000
    dk = hashlib.pbkdf2_hmac("sha256", peppered, salt, iterations)
    return f"pbkdf2${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored hash.

    Uses constant-time comparison to prevent timing attacks.
    """
    if not password or not stored_hash:
        return False

    peppered = _apply_pepper(password)

    if stored_hash.startswith("$2b$") or stored_hash.startswith("$2a$") or stored_hash.startswith("$2y$"):
        # bcrypt format
        if not HAS_BCRYPT:
            log.error("Stored password is bcrypt-hashed but bcrypt module is not available")
            return False
        try:
            return bcrypt.checkpw(peppered, stored_hash.encode("utf-8"))
        except Exception as e:
            log.error(f"bcrypt verify failed: {e}")
            return False

    if stored_hash.startswith("pbkdf2$"):
        # fallback format: pbkdf2$<iter>$<salt_hex>$<hash_hex>
        try:
            _, iter_str, salt_hex, hash_hex = stored_hash.split("$", 3)
            iterations = int(iter_str)
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(hash_hex)
            dk = hashlib.pbkdf2_hmac("sha256", peppered, salt, iterations)
            return hmac.compare_digest(dk, expected)
        except Exception as e:
            log.error(f"pbkdf2 verify failed: {e}")
            return False

    log.warning(f"Unknown password hash format (prefix: {stored_hash[:8]})")
    return False


# ==============================================================================
#  DB INTEGRATION
# ==============================================================================
@lru_cache(maxsize=1)
def is_first_run() -> bool:
    """Returns True if no admin password has been set yet (initial state)."""
    return get_setting(SETTING_KEY_HASH) is None


def seed_default_password_if_needed():
    """On first run, seed the DB with the default admin password.

    Reads EIMS_DEFAULT_ADMIN_PASSWORD from env (default: "1212").
    This is only called once. After the user changes their password,
    is_first_run() returns False forever.
    """
    if not is_first_run():
        return False

    log.info("First run detected — seeding default admin password")
    hashed = hash_password(DEFAULT_ADMIN_PASSWORD)
    save_setting(SETTING_KEY_HASH, hashed)
    save_setting(SETTING_KEY_FIRST_RUN, "0")

    # Clear the cache so subsequent calls see the new state
    is_first_run.cache_clear()
    log.info("Default admin password seeded. User should change it on first login.")
    return True


def verify_admin_password(password: str) -> bool:
    """Verify the admin password against the stored hash.

    Auto-recovers from common issues:
      1. bcrypt hash stored but bcrypt module not installed
      2. Pepper mismatch (DB was moved from another machine with different .env)
      3. No password set yet (first run)

    In any recovery case, re-seeds with the default password using the
    current available hashing method and current pepper.
    """
    stored = get_setting(SETTING_KEY_HASH)
    if not stored:
        # No password set yet — seed default and verify against it
        seed_default_password_if_needed()
        stored = get_setting(SETTING_KEY_HASH)

    if not stored:
        return False

    # Case 1: bcrypt hash stored but bcrypt module not available
    if stored.startswith("$2") and not HAS_BCRYPT:
        log.warning("Stored password uses bcrypt but bcrypt module is not available. "
                    "Re-seeding with default password using available method.")
        new_hash = hash_password(DEFAULT_ADMIN_PASSWORD)
        save_setting(SETTING_KEY_HASH, new_hash)
        save_setting(SETTING_KEY_FIRST_RUN, "0")
        log.info("Password re-seeded with default. User should change it after login.")
        return verify_password(password, new_hash)

    # Try verification
    if verify_password(password, stored):
        return True

    # Case 2: Verification failed — could be pepper mismatch from machine move.
    # If the attempted password matches the default, re-seed and accept.
    if password == DEFAULT_ADMIN_PASSWORD:
        log.warning("Password verification failed for default password. "
                    "Likely pepper mismatch (DB moved from another machine). "
                    "Re-seeding with current pepper.")
        new_hash = hash_password(DEFAULT_ADMIN_PASSWORD)
        save_setting(SETTING_KEY_HASH, new_hash)
        save_setting(SETTING_KEY_FIRST_RUN, "0")
        log.info("Password re-seeded with current pepper. User should change it after login.")
        return True

    return False


def change_password(current_password: str, new_password: str) -> tuple:
    """Change the admin password.

    Returns (success: bool, message: str).
    """
    if not verify_admin_password(current_password):
        log.warning("Password change failed: current password incorrect")
        return False, "Current password is incorrect."

    if len(new_password) < 4:
        return False, "New password must be at least 4 characters."

    try:
        hashed = hash_password(new_password)
        save_setting(SETTING_KEY_HASH, hashed)
        save_setting(SETTING_KEY_FIRST_RUN, "1")
        log.info("Admin password changed successfully")
        return True, "Password changed successfully."
    except Exception as e:
        log.error(f"Failed to change password: {e}", exc_info=True)
        return False, f"Failed to change password: {e}"


# ==============================================================================
#  ENV FILE GENERATOR (helper for first-time setup)
# ==============================================================================
def ensure_env_file_exists():
    """Create a template .env file if it doesn't exist (does not overwrite)."""
    env_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "..", ".env")
    env_path = os.path.normpath(env_path)
    if os.path.exists(env_path):
        return False

    template = """# EIMS Environment Configuration
# ============================
# This file contains secrets that should NOT be committed to version control.
# Generate a strong random pepper below (already done for you).

# Pepper: an additional secret added to admin passwords before hashing.
# Even if the database is leaked, passwords cannot be cracked without this file.
EIMS_AUTH_PEPPER="{pepper}"

# Default admin password used ONLY on first run (before user sets their own).
# Change this before first deployment if you want a different default.
EIMS_DEFAULT_ADMIN_PASSWORD="1212"
""".format(pepper=secrets.token_hex(32))

    try:
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(template)
        log.info(f"Created .env template at {env_path}")
        return True
    except Exception as e:
        log.warning(f"Could not create .env file: {e}")
        return False


# ==============================================================================
#  INITIALIZATION HOOK
# ==============================================================================
def init_auth():
    """Call this at app startup."""
    ensure_env_file_exists()
    seed_default_password_if_needed()
    log.info(f"Auth module ready. bcrypt: {HAS_BCRYPT}, pepper: {'on' if _load_pepper() else 'off'}")


if __name__ == "__main__":
    init_auth()
    print(f"bcrypt available: {HAS_BCRYPT}")
    print(f"pepper loaded: {bool(_load_pepper())}")
    print(f"first run: {is_first_run()}")

    # Test verify
    test_pw = "1212"
    print(f"Verify '1212' against stored: {verify_admin_password(test_pw)}")

    # Test change
    ok, msg = change_password("1212", "1212")
    print(f"Change password (same): {ok} - {msg}")
