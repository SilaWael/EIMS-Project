# -*- coding: utf-8 -*-
"""
EIMS Database Layer v2
======================
Handles all SQLite operations with the new hierarchical classification schema.
"""
import sqlite3
import json
import os
import re
import shutil
from datetime import datetime

from core.logger import get_logger

log = get_logger(__name__)

DB_NAME = "eims.db"
ARCHIVE_DIR = "pdf_archive"


# ==============================================================================
#  CONNECTION HELPERS
# ==============================================================================
def get_conn():
    # Use module-level DB_NAME so monkeypatching in tests works
    return sqlite3.connect(DB_NAME)


def ensure_dirs():
    """Ensure required directories exist. Uses exist_ok for safety on Windows."""
    if not os.path.isdir(ARCHIVE_DIR):
        try:
            os.makedirs(ARCHIVE_DIR, exist_ok=True)
        except FileExistsError:
            # Directory was created by another process between the check and makedirs
            pass


# ==============================================================================
#  SCHEMA INITIALIZATION
# ==============================================================================
def init_db():
    """Initializes the full v2 schema: reference tables + master_registry extensions."""
    ensure_dirs()
    conn = get_conn()
    c = conn.cursor()

    # --- Master registry (created in v1; create if missing) ---
    c.execute("""
        CREATE TABLE IF NOT EXISTS master_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date TEXT NOT NULL,
            category TEXT,
            sub_category TEXT,
            location TEXT,
            quantity REAL NOT NULL,
            unit TEXT NOT NULL,
            status TEXT NOT NULL,
            remarks TEXT,
            pdf_filename TEXT,
            pdf_path TEXT,
            detailed_levels TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # --- v2 Reference tables (hierarchical classification) ---
    c.execute("""
        CREATE TABLE IF NOT EXISTS ref_discipline (
            id INTEGER PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            name_en TEXT NOT NULL,
            name_ar TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS ref_system (
            id INTEGER PRIMARY KEY,
            discipline_id INTEGER NOT NULL,
            code TEXT UNIQUE NOT NULL,
            name_en TEXT NOT NULL,
            name_ar TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            FOREIGN KEY (discipline_id) REFERENCES ref_discipline(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS ref_component (
            id INTEGER PRIMARY KEY,
            system_id INTEGER NOT NULL,
            code TEXT NOT NULL,
            name_en TEXT NOT NULL,
            name_ar TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            FOREIGN KEY (system_id) REFERENCES ref_system(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS ref_work_type (
            id INTEGER PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            name_en TEXT NOT NULL,
            name_ar TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS ref_stage (
            id INTEGER PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            name_en TEXT NOT NULL,
            name_ar TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS ref_road (
            id INTEGER PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            name_en TEXT,
            name_ar TEXT,
            road_type TEXT,
            sort_order INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS ref_asset_segment (
            id INTEGER PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            name_en TEXT NOT NULL,
            name_ar TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0
        )
    """)

    # --- v2 columns on master_registry (migration-safe) ---
    c.execute("PRAGMA table_info(master_registry)")
    existing_cols = {col[1] for col in c.fetchall()}

    new_cols = [
        ("stationing", "TEXT"),
        ("activity_detail", "TEXT"),
        ("discipline_id", "INTEGER"),
        ("system_id", "INTEGER"),
        ("component_id", "INTEGER"),
        ("work_type_id", "INTEGER"),
        ("stage_id", "INTEGER"),
        ("road_id", "INTEGER"),
        ("asset_segment_id", "INTEGER"),
        ("location_note", "TEXT"),
        ("pdf_blob", "BLOB"),          # NEW: PDF content stored as binary (for Streamlit Cloud)
        ("pdf_blob_size", "INTEGER"),  # NEW: size in bytes (for display)
        ("html_blob", "BLOB"),         # NEW: HTML content stored as binary
    ]
    for col_name, col_type in new_cols:
        if col_name not in existing_cols:
            c.execute(f"ALTER TABLE master_registry ADD COLUMN {col_name} {col_type}")

    # --- Performance indexes ---
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS idx_mr_report_date ON master_registry(report_date)",
        "CREATE INDEX IF NOT EXISTS idx_mr_discipline ON master_registry(discipline_id)",
        "CREATE INDEX IF NOT EXISTS idx_mr_system ON master_registry(system_id)",
        "CREATE INDEX IF NOT EXISTS idx_mr_road ON master_registry(road_id)",
        "CREATE INDEX IF NOT EXISTS idx_mr_status ON master_registry(status)",
    ]:
        c.execute(idx_sql)

    conn.commit()
    conn.close()


# ==============================================================================
#  SETTINGS
# ==============================================================================
def save_setting(key, value):
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)",
                  (key, str(value)))
        conn.commit()
    except Exception as e:
        log.error(f"Failed to save setting '{key}': {e}", exc_info=True)
    finally:
        conn.close()


def get_setting(key, default=None):
    conn = get_conn()
    c = conn.cursor()
    val = default
    try:
        c.execute("SELECT value FROM system_settings WHERE key = ?", (key,))
        row = c.fetchone()
        if row:
            val = row[0]
    except Exception as e:
        log.error(f"Failed to read setting '{key}': {e}", exc_info=True)
    finally:
        conn.close()
    return val


# ==============================================================================
#  DATE HELPERS
# ==============================================================================
def normalize_date_to_db(date_str):
    if not date_str:
        return None
    date_str = str(date_str).strip()
    if date_str.endswith(".0"):
        date_str = date_str[:-2]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return date_str


def format_date_to_display(date_str):
    if not date_str:
        return ""
    date_str = str(date_str).strip()
    if date_str.endswith(".0"):
        date_str = date_str[:-2]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%d-%m-%Y")
        except ValueError:
            pass
    return date_str


# ==============================================================================
#  REFERENCE DATA ACCESS
# ==============================================================================
def list_disciplines(lang='en'):
    conn = get_conn()
    col = 'name_en' if lang == 'en' else 'name_ar'
    rows = conn.execute(
        f"SELECT id, code, {col} FROM ref_discipline ORDER BY sort_order, id"
    ).fetchall()
    conn.close()
    return rows


def list_systems(discipline_id, lang='en'):
    conn = get_conn()
    col = 'name_en' if lang == 'en' else 'name_ar'
    rows = conn.execute(
        f"SELECT id, code, {col} FROM ref_system WHERE discipline_id=? ORDER BY sort_order, id",
        (discipline_id,)
    ).fetchall()
    conn.close()
    return rows


def list_components(system_id, lang='en'):
    conn = get_conn()
    col = 'name_en' if lang == 'en' else 'name_ar'
    rows = conn.execute(
        f"SELECT id, code, {col} FROM ref_component WHERE system_id=? ORDER BY sort_order, id",
        (system_id,)
    ).fetchall()
    conn.close()
    return rows


def list_work_types(lang='en'):
    conn = get_conn()
    col = 'name_en' if lang == 'en' else 'name_ar'
    rows = conn.execute(
        f"SELECT id, code, {col} FROM ref_work_type ORDER BY sort_order, id"
    ).fetchall()
    conn.close()
    return rows


def list_stages(lang='en'):
    conn = get_conn()
    col = 'name_en' if lang == 'en' else 'name_ar'
    rows = conn.execute(
        f"SELECT id, code, {col} FROM ref_stage ORDER BY sort_order, id"
    ).fetchall()
    conn.close()
    return rows


def list_roads(lang='en'):
    conn = get_conn()
    col = 'name_en' if lang == 'en' else 'name_ar'
    rows = conn.execute(
        f"SELECT id, code, COALESCE({col}, code) FROM ref_road ORDER BY sort_order, id"
    ).fetchall()
    conn.close()
    return rows


def list_asset_segments(lang='en'):
    conn = get_conn()
    col = 'name_en' if lang == 'en' else 'name_ar'
    rows = conn.execute(
        f"SELECT id, code, {col} FROM ref_asset_segment ORDER BY sort_order, id"
    ).fetchall()
    conn.close()
    return rows


def get_class_label(table, item_id, lang='en'):
    """Returns the label of a reference item by id."""
    if not item_id:
        return ""
    col = 'name_en' if lang == 'en' else 'name_ar'
    conn = get_conn()
    row = conn.execute(
        f"SELECT {col} FROM {table} WHERE id=?", (item_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else ""


# ==============================================================================
#  RECORD CRUD
# ==============================================================================
def save_record(rec):
    """Insert a new record. `rec` is a dict with v2 fields."""
    conn = get_conn()
    c = conn.cursor()

    # Handle PDF archiving
    pdf_filename = rec.get('pdf_filename')
    pdf_path = rec.get('pdf_path')
    pdf_bytes = rec.get('pdf_bytes')

    if pdf_bytes is not None:
        safe_date = (rec['report_date'] or 'unknown').replace("-", "")
        safe_disc = (rec.get('discipline_code') or 'misc').replace(" ", "_")
        safe_comp = (rec.get('component_code') or 'item').replace(" ", "_").replace("/", "_")
        original_ext = os.path.splitext(rec.get('original_filename') or '.pdf')[1]
        pdf_filename = f"{safe_date}_{safe_disc}_{safe_comp}{original_ext}"
        pdf_path = os.path.join(ARCHIVE_DIR, pdf_filename)
        if isinstance(pdf_bytes, bytes):
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)
        else:
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes.getbuffer())
    elif rec.get('original_filename'):
        # Auto-link
        current_dir = os.path.abspath(os.path.dirname(__file__))
        outer_dir = os.path.dirname(current_dir)
        search_dirs = []
        custom_dir = get_setting("custom_pdf_dir", "")
        if custom_dir and os.path.exists(custom_dir):
            search_dirs.append(custom_dir)
        search_dirs.extend([
            os.path.join(outer_dir, 'Finished PDFs'),
            os.path.join(outer_dir, 'Processed_Audits'),
            outer_dir,
            os.path.join(current_dir, 'Processed_Audits'),
            os.path.join(current_dir, 'Finished PDFs')
        ])
        for sd in search_dirs:
            fp = _find_file_case_insensitive(sd, rec['original_filename'])
            if fp:
                pdf_path = fp
                pdf_filename = os.path.basename(fp)
                break

    detailed_levels_json = json.dumps(rec['detailed_levels']) if rec.get('detailed_levels') else None

    c.execute("""
        INSERT INTO master_registry (
            report_date, category, sub_category, location, quantity, unit, status, remarks,
            pdf_filename, pdf_path, detailed_levels, stationing, activity_detail,
            discipline_id, system_id, component_id, work_type_id, stage_id,
            road_id, asset_segment_id, location_note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        normalize_date_to_db(rec.get('report_date')),
        rec.get('category'),
        rec.get('sub_category'),
        rec.get('location'),
        float(rec.get('quantity') or 0),
        rec.get('unit') or 'Unit',
        rec.get('status') or 'Pass',
        rec.get('remarks'),
        pdf_filename,
        pdf_path,
        detailed_levels_json,
        rec.get('stationing'),
        rec.get('activity_detail'),
        rec.get('discipline_id'),
        rec.get('system_id'),
        rec.get('component_id'),
        rec.get('work_type_id'),
        rec.get('stage_id'),
        rec.get('road_id'),
        rec.get('asset_segment_id'),
        rec.get('location_note'),
    ))
    conn.commit()
    conn.close()
    return True


def delete_record(record_id):
    """Delete a single record by ID. Creates a safety backup first."""
    from core.backup import create_backup
    # Convert to native int (handles numpy.int64 from pandas)
    try:
        record_id = int(record_id)
    except (TypeError, ValueError):
        log.error(f"Invalid record_id for deletion: {record_id}")
        return False

    create_backup(f"before_delete_id{record_id}")

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT pdf_path FROM master_registry WHERE id = ?", (record_id,))
    row = c.fetchone()
    if row and row[0]:
        if os.path.exists(row[0]) and ARCHIVE_DIR in row[0]:
            try:
                os.remove(row[0])
            except Exception as e:
                log.warning(f"Could not delete PDF file {row[0]}: {e}")
    c.execute("DELETE FROM master_registry WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()
    log.info(f"Deleted record ID {record_id}")
    return True


def delete_records_bulk(record_ids):
    """Delete multiple records by ID. Single backup for the whole batch."""
    from core.backup import create_backup
    if not record_ids:
        return 0

    # Convert to native ints (handles numpy.int64 from pandas)
    record_ids = [int(rid) for rid in record_ids]

    create_backup(f"before_bulk_delete_{len(record_ids)}")

    conn = get_conn()
    c = conn.cursor()
    placeholders = ",".join("?" * len(record_ids))
    # Delete associated PDFs first
    c.execute(f"SELECT pdf_path FROM master_registry WHERE id IN ({placeholders})", record_ids)
    for row in c.fetchall():
        if row[0] and os.path.exists(row[0]) and ARCHIVE_DIR in row[0]:
            try:
                os.remove(row[0])
            except Exception as e:
                log.warning(f"Could not delete PDF {row[0]}: {e}")
    c.execute(f"DELETE FROM master_registry WHERE id IN ({placeholders})", record_ids)
    deleted = c.rowcount
    conn.commit()
    conn.close()
    log.info(f"Bulk deleted {deleted} records (IDs: {record_ids})")
    return deleted


def reset_database():
    """Factory reset — deletes all records. Creates a safety backup first."""
    from core.backup import create_backup
    create_backup("before_factory_reset")

    conn = get_conn()
    c = conn.cursor()
    # Delete associated PDFs
    c.execute("SELECT pdf_path FROM master_registry")
    for row in c.fetchall():
        if row[0] and os.path.exists(row[0]) and ARCHIVE_DIR in row[0]:
            try:
                os.remove(row[0])
            except Exception as e:
                log.warning(f"Could not delete PDF {row[0]}: {e}")
    c.execute("DELETE FROM master_registry")
    c.execute("DELETE FROM sqlite_sequence WHERE name='master_registry'")
    conn.commit()
    conn.close()
    log.warning("Database factory reset executed — all records wiped")


def _find_file_case_insensitive(directory, filename):
    if not os.path.exists(directory):
        return None
    target = filename.strip().lower()
    for f in os.listdir(directory):
        if f.strip().lower() == target:
            return os.path.abspath(os.path.join(directory, f))
    return None


# ==============================================================================
#  DATA LOAD
# ==============================================================================
def load_data(lang='en'):
    """Returns DataFrame with friendly columns for display."""
    import pandas as pd
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT
            m.*,
            d.name_en  AS discipline_en,  d.name_ar  AS discipline_ar,
            s.name_en  AS system_en,      s.name_ar  AS system_ar,
            c.name_en  AS component_en,   c.name_ar  AS component_ar,
            w.name_en  AS work_type_en,   w.name_ar  AS work_type_ar,
            st.name_en AS stage_en,       st.name_ar AS stage_ar,
            r.code     AS road_code,
            seg.name_en AS segment_en,    seg.name_ar AS segment_ar
        FROM master_registry m
        LEFT JOIN ref_discipline d ON m.discipline_id = d.id
        LEFT JOIN ref_system s ON m.system_id = s.id
        LEFT JOIN ref_component c ON m.component_id = c.id
        LEFT JOIN ref_work_type w ON m.work_type_id = w.id
        LEFT JOIN ref_stage st ON m.stage_id = st.id
        LEFT JOIN ref_road r ON m.road_id = r.id
        LEFT JOIN ref_asset_segment seg ON m.asset_segment_id = seg.id
        ORDER BY m.report_date DESC, m.id DESC
    """, conn)
    conn.close()
    if not df.empty and 'report_date' in df.columns:
        df['report_date'] = df['report_date'].apply(format_date_to_display)
    return df


def count_records():
    """Fast record count without loading all columns."""
    # Import DB_NAME dynamically so monkeypatching in tests works
    conn = sqlite3.connect(DB_NAME)
    try:
        row = conn.execute("SELECT COUNT(*) FROM master_registry").fetchone()
        return row[0] if row else 0
    except Exception as e:
        log.error(f"Failed to count records: {e}", exc_info=True)
        return 0
    finally:
        conn.close()


# ==============================================================================
#  PDF BLOB STORAGE (for Streamlit Cloud / portable deployment)
# ==============================================================================
def save_pdf_blob(record_id, pdf_bytes):
    """Store a PDF file's bytes directly in the database.

    Useful for Streamlit Cloud where the filesystem is ephemeral.
    """
    if not pdf_bytes or not record_id:
        return False
    try:
        record_id = int(record_id)
    except (TypeError, ValueError):
        return False

    conn = get_conn()
    c = conn.cursor()
    try:
        if isinstance(pdf_bytes, bytes):
            blob_data = pdf_bytes
        else:
            # Streamlit UploadedFile - read bytes
            blob_data = pdf_bytes.read() if hasattr(pdf_bytes, 'read') else bytes(pdf_bytes)

        c.execute(
            "UPDATE master_registry SET pdf_blob = ?, pdf_blob_size = ? WHERE id = ?",
            (blob_data, len(blob_data), record_id)
        )
        conn.commit()
        log.info(f"PDF BLOB stored for record {record_id} ({len(blob_data)} bytes)")
        return True
    except Exception as e:
        log.error(f"Failed to store PDF BLOB for record {record_id}: {e}", exc_info=True)
        return False
    finally:
        conn.close()


def save_html_blob(record_id, html_bytes):
    """Store an HTML file's bytes directly in the database."""
    if not html_bytes or not record_id:
        return False
    try:
        record_id = int(record_id)
    except (TypeError, ValueError):
        return False

    conn = get_conn()
    c = conn.cursor()
    try:
        if isinstance(html_bytes, bytes):
            blob_data = html_bytes
        else:
            blob_data = html_bytes.read() if hasattr(html_bytes, 'read') else bytes(html_bytes)

        c.execute(
            "UPDATE master_registry SET html_blob = ? WHERE id = ?",
            (blob_data, record_id)
        )
        conn.commit()
        log.info(f"HTML BLOB stored for record {record_id} ({len(blob_data)} bytes)")
        return True
    except Exception as e:
        log.error(f"Failed to store HTML BLOB for record {record_id}: {e}", exc_info=True)
        return False
    finally:
        conn.close()


def get_pdf_blob(record_id):
    """Retrieve PDF bytes for a record. Returns bytes or None."""
    try:
        record_id = int(record_id)
    except (TypeError, ValueError):
        return None

    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT pdf_blob FROM master_registry WHERE id = ?", (record_id,)
        ).fetchone()
        return row[0] if row and row[0] else None
    except Exception as e:
        log.error(f"Failed to read PDF BLOB for record {record_id}: {e}")
        return None
    finally:
        conn.close()


def get_html_blob(record_id):
    """Retrieve HTML bytes for a record. Returns bytes or None."""
    try:
        record_id = int(record_id)
    except (TypeError, ValueError):
        return None

    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT html_blob FROM master_registry WHERE id = ?", (record_id,)
        ).fetchone()
        return row[0] if row and row[0] else None
    except Exception as e:
        log.error(f"Failed to read HTML BLOB for record {record_id}: {e}")
        return None
    finally:
        conn.close()


def list_records_with_blobs():
    """Returns a list of records that have PDF blobs stored.
    Each item: (id, report_date, sub_category, pdf_filename, pdf_blob_size, has_html)
    """
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT id, report_date, sub_category, pdf_filename,
                   COALESCE(pdf_blob_size, 0), html_blob IS NOT NULL
            FROM master_registry
            WHERE pdf_blob IS NOT NULL
            ORDER BY report_date DESC, id DESC
        """).fetchall()
        return rows
    except Exception as e:
        log.error(f"Failed to list records with blobs: {e}")
        return []
    finally:
        conn.close()


def migrate_existing_pdfs_to_blobs():
    """One-time migration: read existing PDFs from disk and store as BLOBs.

    Useful when transitioning from local filesystem storage to BLOB storage
    (e.g. before deploying to Streamlit Cloud).
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, pdf_path FROM master_registry WHERE pdf_path IS NOT NULL AND pdf_blob IS NULL"
    ).fetchall()
    conn.close()

    migrated = 0
    for rec_id, pdf_path in rows:
        if pdf_path and os.path.exists(pdf_path):
            try:
                with open(pdf_path, 'rb') as f:
                    pdf_bytes = f.read()
                if save_pdf_blob(rec_id, pdf_bytes):
                    migrated += 1
            except Exception as e:
                log.warning(f"Could not migrate PDF {pdf_path}: {e}")

    log.info(f"Migrated {migrated} PDFs from filesystem to BLOB storage")
    return migrated


if __name__ == "__main__":
    init_db()
    print("[OK] Database schema initialized.")
    print(f"[OK] Records in DB: {count_records()}")
