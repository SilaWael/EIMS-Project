# -*- coding: utf-8 -*-
"""
EIMS Backup Module
==================
Automatic database backups before destructive operations
(delete single / delete bulk / factory reset).

Backup strategy:
  - File-level copy of eims.db to backups/eims_YYYY-MM-DD_HHMMSS_<reason>.db
  - Keeps the last N backups (default: 20); older ones auto-pruned
  - Optional: ZIP archive for portability
"""
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from core.logger import get_logger

log = get_logger(__name__)


# ==============================================================================
#  CONSTANTS
# ==============================================================================
BACKUP_DIR = "backups"
DB_NAME = "eims.db"
MAX_BACKUPS = 20  # auto-prune older backups beyond this count


# ==============================================================================
#  HELPERS
# ==============================================================================
def _ensure_backup_dir():
    if not os.path.isdir(BACKUP_DIR):
        try:
            os.makedirs(BACKUP_DIR, exist_ok=True)
        except FileExistsError:
            pass


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


def _prune_old_backups():
    """Keep only the most recent MAX_BACKUPS files."""
    try:
        files = []
        for f in os.listdir(BACKUP_DIR):
            if f.startswith("eims_") and f.endswith(".db"):
                fp = os.path.join(BACKUP_DIR, f)
                files.append((fp, os.path.getmtime(fp)))
        if len(files) <= MAX_BACKUPS:
            return
        files.sort(key=lambda x: x[1])  # oldest first
        to_delete = files[:len(files) - MAX_BACKUPS]
        for fp, _ in to_delete:
            try:
                os.remove(fp)
                log.info(f"Pruned old backup: {os.path.basename(fp)}")
            except Exception as e:
                log.warning(f"Failed to prune {fp}: {e}")
    except Exception as e:
        log.warning(f"Backup pruning failed: {e}", exc_info=True)


# ==============================================================================
#  PUBLIC API
# ==============================================================================
def create_backup(reason: str = "manual") -> str | None:
    """Create a timestamped backup of the database.

    Args:
        reason: short tag included in filename (e.g. "before_delete", "before_reset")

    Returns:
        Path to the backup file, or None on failure.
    """
    # Import DB_NAME dynamically so monkeypatching in tests works
    from database import DB_NAME as current_db_name

    _ensure_backup_dir()

    if not os.path.exists(current_db_name):
        log.warning(f"Cannot backup: database file {current_db_name} not found")
        return None

    # Sanitize reason for filename safety
    safe_reason = "".join(c for c in reason if c.isalnum() or c in "_-") or "manual"
    backup_name = f"eims_{_timestamp()}_{safe_reason}.db"
    backup_path = os.path.join(BACKUP_DIR, backup_name)

    try:
        # Use SQLite backup API for a consistent snapshot (handles in-flight transactions)
        src = sqlite3.connect(current_db_name)
        dst = sqlite3.connect(backup_path)
        src.backup(dst)
        dst.close()
        src.close()

        size_kb = os.path.getsize(backup_path) / 1024
        log.info(f"Backup created: {backup_name} ({size_kb:.1f} KB) — reason: {reason}")
        _prune_old_backups()
        return backup_path
    except Exception as e:
        log.error(f"Backup failed: {e}", exc_info=True)
        # Clean up partial backup if exists
        if os.path.exists(backup_path):
            try:
                os.remove(backup_path)
            except Exception:
                pass
        return None


def list_backups() -> list:
    """Return a list of available backups (newest first).

    Each item is a dict: {path, name, size_kb, created_at}
    """
    if not os.path.isdir(BACKUP_DIR):
        return []

    backups = []
    for f in os.listdir(BACKUP_DIR):
        if not (f.startswith("eims_") and f.endswith(".db")):
            continue
        fp = os.path.join(BACKUP_DIR, f)
        try:
            stat = os.stat(fp)
            backups.append({
                "path": fp,
                "name": f,
                "size_kb": stat.st_size / 1024,
                "created_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            })
        except Exception as e:
            log.warning(f"Failed to stat {fp}: {e}")

    backups.sort(key=lambda x: x["created_at"], reverse=True)
    return backups


def restore_from_backup(backup_path: str) -> tuple:
    """Restore the database from a backup file.

    Returns (success: bool, message: str).
    """
    if not os.path.exists(backup_path):
        return False, f"Backup file not found: {backup_path}"

    # Create a safety backup of the current DB before overwriting
    safety = create_backup("before_restore")
    log.info(f"Safety backup created before restore: {safety}")

    try:
        # Close any active connections by copying at filesystem level
        # (caller must ensure no Streamlit rerun is in flight)
        shutil.copy2(backup_path, DB_NAME)
        log.info(f"Database restored from: {os.path.basename(backup_path)}")
        return True, f"Restored from {os.path.basename(backup_path)}"
    except Exception as e:
        log.error(f"Restore failed: {e}", exc_info=True)
        return False, f"Restore failed: {e}"


def delete_backup(backup_path: str) -> bool:
    """Delete a specific backup file."""
    if not os.path.exists(backup_path):
        return False
    try:
        os.remove(backup_path)
        log.info(f"Deleted backup: {os.path.basename(backup_path)}")
        return True
    except Exception as e:
        log.error(f"Failed to delete backup {backup_path}: {e}")
        return False


if __name__ == "__main__":
    print("Creating test backup...")
    path = create_backup("test_run")
    print(f"Created: {path}")

    print("\nAvailable backups:")
    for b in list_backups():
        print(f"  {b['name']:50s}  {b['size_kb']:8.1f} KB  {b['created_at']}")
