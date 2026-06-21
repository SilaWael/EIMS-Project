# -*- coding: utf-8 -*-
"""
EIMS Password Reset Script
===========================
Run this once if you can't log in because:
  - bcrypt is not installed on your machine
  - The stored password hash is in bcrypt format
  - You forgot your admin password

Usage:
    py reset_password.py
    (or) python reset_password.py

It will reset the admin password to the default "1212" using whatever
hashing method is available on your system (bcrypt preferred, pbkdf2 fallback).
"""
import sys
import os

# Ensure local imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.logger import get_logger
from database import get_setting, save_setting
from auth.auth import hash_password, HAS_BCRYPT, _load_pepper

log = get_logger(__name__)


def reset_password():
    print("=" * 60)
    print("EIMS Password Reset Tool")
    print("=" * 60)
    print()
    print(f"bcrypt available: {HAS_BCRYPT}")
    print(f"pepper loaded:    {bool(_load_pepper())}")
    print()

    # Show current state
    current_hash = get_setting("admin_password_hash")
    if current_hash:
        prefix = current_hash[:8] + "..."
        print(f"Current password hash prefix: {prefix}")
        if current_hash.startswith("$2b$") and not HAS_BCRYPT:
            print(">> PROBLEM DETECTED: stored hash is bcrypt but bcrypt is not installed.")
            print(">> This is why login fails. Resetting now...")
        print()
    else:
        print("No password currently set. Will seed default.")
        print()

    # Reset
    new_hash = hash_password("1212")
    save_setting("admin_password_hash", new_hash)
    save_setting("admin_first_run_done", "0")

    print("=" * 60)
    print("[OK] Password has been reset to: 1212")
    print("=" * 60)
    print()
    print("You can now log in to the EIMS Importer page with password: 1212")
    print()
    print("IMPORTANT: After logging in, please change the password via the")
    print("'Change Admin Password' section at the bottom of the importer page.")
    print()
    print(f"Hashing method used: {'bcrypt' if new_hash.startswith('$2b$') else 'pbkdf2'}")
    if not HAS_BCRYPT:
        print()
        print("RECOMMENDED: Install bcrypt for stronger security:")
        print("    pip install bcrypt")
        print("After installing, run this script again to upgrade to bcrypt.")


if __name__ == "__main__":
    try:
        reset_password()
    except Exception as e:
        print(f"[ERROR] {e}")
        log.error("Password reset failed", exc_info=True)
        sys.exit(1)
    input("\nPress Enter to exit...")
