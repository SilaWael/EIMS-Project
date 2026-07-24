"""
EIMS Database Layer — Supabase Postgres adapter.
Replaces the original SQLite functions from app.py with cloud equivalents.
"""
import os
import json
import re
import psycopg2
import psycopg2.extras
from datetime import datetime
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from supabase import create_client, Client

# Load env from .env if present (local dev), else rely on Streamlit secrets
load_dotenv()


def _get_config():
    """Get config from environment, .env, or Streamlit secrets."""
    # Try environment first
    cfg = {
        'SUPABASE_URL': os.environ.get('SUPABASE_URL'),
        'SUPABASE_ANON_KEY': os.environ.get('SUPABASE_ANON_KEY'),
        'SUPABASE_SERVICE_ROLE_KEY': os.environ.get('SUPABASE_SERVICE_ROLE_KEY'),
        'DB_PASSWORD': os.environ.get('SUPABASE_DB_PASSWORD') or os.environ.get('DB_PASSWORD'),
        'PROJECT_REF': os.environ.get('SUPABASE_PROJECT_REF') or os.environ.get('PROJECT_REF'),
        'POOLER_HOST': os.environ.get('POOLER_HOST', 'aws-0-ap-southeast-1.pooler.supabase.com'),
        'BUCKET_PDFS': os.environ.get('STORAGE_BUCKET_PDFS', 'finished-pdfs'),
        'BUCKET_AUDITS': os.environ.get('STORAGE_BUCKET_AUDITS', 'processed-audits'),
        'BUCKET_CSVS': os.environ.get('STORAGE_BUCKET_CSVS', 'csv-database'),
        'ADMIN_PASSWORD': os.environ.get('ADMIN_PASSWORD', '1212'),
    }

    # If running in Streamlit Cloud, try st.secrets
    missing = [k for k, v in cfg.items() if v is None and k != 'ADMIN_PASSWORD']
    if missing:
        try:
            import streamlit as st
            if hasattr(st, 'secrets'):
                secrets = st.secrets
                if 'database' in secrets:
                    cfg['SUPABASE_URL'] = cfg['SUPABASE_URL'] or secrets['database'].get('SUPABASE_URL')
                    cfg['SUPABASE_ANON_KEY'] = cfg['SUPABASE_ANON_KEY'] or secrets['database'].get('SUPABASE_ANON_KEY')
                    cfg['SUPABASE_SERVICE_ROLE_KEY'] = cfg['SUPABASE_SERVICE_ROLE_KEY'] or secrets['database'].get('SUPABASE_SERVICE_ROLE_KEY')
                    cfg['DB_PASSWORD'] = cfg['DB_PASSWORD'] or secrets['database'].get('DB_PASSWORD')
                    cfg['PROJECT_REF'] = cfg['PROJECT_REF'] or secrets['database'].get('PROJECT_REF')
                    cfg['POOLER_HOST'] = cfg['POOLER_HOST'] or secrets['database'].get('POOLER_HOST', 'aws-0-ap-southeast-1.pooler.supabase.com')
                if 'storage' in secrets:
                    cfg['BUCKET_PDFS'] = secrets['storage'].get('BUCKET_PDFS', cfg['BUCKET_PDFS'])
                    cfg['BUCKET_AUDITS'] = secrets['storage'].get('BUCKET_AUDITS', cfg['BUCKET_AUDITS'])
                    cfg['BUCKET_CSVS'] = secrets['storage'].get('BUCKET_CSVS', cfg['BUCKET_CSVS'])
                if 'app' in secrets:
                    cfg['ADMIN_PASSWORD'] = secrets['app'].get('ADMIN_PASSWORD', cfg['ADMIN_PASSWORD'])
        except Exception:
            pass

    return cfg


CONFIG = _get_config()


# ============================================================
# Connection helpers
# ============================================================

def get_pg_connection():
    """Get a direct Postgres connection via Supabase pooler (IPv4)."""
    if not all([CONFIG['DB_PASSWORD'], CONFIG['PROJECT_REF']]):
        raise RuntimeError("Missing DB credentials. Set DB_PASSWORD and PROJECT_REF.")
    user = f"postgres.{CONFIG['PROJECT_REF']}"
    conn_str = f"postgresql://{user}:{CONFIG['DB_PASSWORD']}@{CONFIG['POOLER_HOST']}:5432/postgres"
    return psycopg2.connect(conn_str, connect_timeout=30)


def get_supabase_client() -> Client:
    """Get a Supabase client (REST + Storage)."""
    return create_client(CONFIG['SUPABASE_URL'], CONFIG['SUPABASE_SERVICE_ROLE_KEY'])


# ============================================================
# Date helpers (preserved from original app.py)
# ============================================================

def normalize_date_to_db(date_str):
    if not date_str:
        return datetime.now().strftime("%Y-%m-%d")
    s = str(date_str).strip()
    if s.endswith(".0"):
        s = s[:-2]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return s


def format_date_to_display(date_str):
    """Convert YYYY-MM-DD to DD-MM-YYYY for display."""
    if not date_str:
        return ""
    s = str(date_str).strip()
    if s.endswith(".0"):
        s = s[:-2]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%d-%m-%Y")
        except ValueError:
            pass
    return s


# ============================================================
# CRUD operations
# ============================================================

def load_data():
    """Load all records from master_registry as a list of dicts."""
    conn = get_pg_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT id, report_date, category, sub_category, location,
                   quantity, unit, status, remarks, pdf_filename, pdf_path,
                   detailed_levels, stationing, activity_detail,
                   created_at, updated_at
            FROM master_registry
            ORDER BY id
        """)
        rows = cur.fetchall()
        # Convert date to string for compatibility
        for r in rows:
            if r.get('report_date'):
                r['report_date'] = r['report_date'].strftime('%d-%m-%Y') if hasattr(r['report_date'], 'strftime') else str(r['report_date'])
            if r.get('detailed_levels'):
                if isinstance(r['detailed_levels'], str):
                    try:
                        r['detailed_levels'] = r['detailed_levels']
                    except Exception:
                        pass
                # keep as dict/list for streamlit
            else:
                r['detailed_levels'] = None
        return rows
    finally:
        conn.close()


def save_record(report_date, category, sub_category, location, quantity, unit,
                status, remarks, detailed_levels_list=None,
                original_filename=None, stationing=None, activity_detail=None,
                pdf_bytes=None):
    """
    Insert a new record into master_registry.

    If pdf_bytes is provided, uploads to Storage first.
    If only original_filename is provided, builds a public URL by name (file should already be in storage).
    """
    sb = get_supabase_client()
    report_date = normalize_date_to_db(report_date)

    pdf_filename = None
    pdf_path = None

    if pdf_bytes is not None and original_filename:
        # Upload bytes to Storage
        ext = os.path.splitext(original_filename)[1].lower()
        ct_map = {'.pdf': 'application/pdf', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png'}
        content_type = ct_map.get(ext, 'application/octet-stream')
        try:
            sb.storage.from_(CONFIG['BUCKET_PDFS']).upload(
                path=original_filename,
                file=pdf_bytes,
                file_options={"content-type": content_type, "upsert": "true"}
            )
            pdf_filename = original_filename
            pdf_path = sb.storage.from_(CONFIG['BUCKET_PDFS']).get_public_url(original_filename)
        except Exception as e:
            print(f"Storage upload failed: {e}")
            pdf_filename = original_filename
            pdf_path = None
    elif original_filename:
        # File should already be in storage — build URL by name
        pdf_filename = original_filename
        pdf_path = f"{CONFIG['SUPABASE_URL']}/storage/v1/object/public/{CONFIG['BUCKET_PDFS']}/{original_filename}"

    # Auto-extract stationing from location if not provided
    if not stationing and location:
        m = re.search(r'(\d+\+\d+\s*(?:to|-|–)\s*\d+\+\d+)', location)
        if m:
            stationing = m.group(1)

    detailed_levels_json = json.dumps(detailed_levels_list) if detailed_levels_list else None

    conn = get_pg_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO master_registry (
                report_date, category, sub_category, location, quantity, unit,
                status, remarks, pdf_filename, pdf_path, detailed_levels,
                stationing, activity_detail
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            report_date, category, sub_category, location, float(quantity), unit,
            status, remarks, pdf_filename, pdf_path, detailed_levels_json,
            stationing, activity_detail
        ))
        new_id = cur.fetchone()[0]
        conn.commit()
        return new_id
    finally:
        conn.close()


def delete_record(record_id: int) -> bool:
    """Delete a record by ID."""
    conn = get_pg_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM master_registry WHERE id = %s", (record_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def check_duplicate(report_date, sub_category, location, stationing, pdf_filename) -> bool:
    """Idempotency check — returns True if a duplicate exists."""
    rd = normalize_date_to_db(report_date)
    conn = get_pg_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT 1 FROM master_registry
            WHERE report_date = %s AND sub_category = %s AND location = %s
              AND COALESCE(stationing,'') = COALESCE(%s,'')
              AND COALESCE(pdf_filename,'') = COALESCE(%s,'')
            LIMIT 1
        """, (rd, sub_category, location, stationing or '', pdf_filename or ''))
        return cur.fetchone() is not None
    finally:
        conn.close()


# ============================================================
# Settings
# ============================================================

def save_setting(key: str, value: str):
    conn = get_pg_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO system_settings (key, value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """, (key, str(value)))
        conn.commit()
    finally:
        conn.close()


def get_setting(key: str, default=None) -> Optional[str]:
    conn = get_pg_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT value FROM system_settings WHERE key = %s", (key,))
        row = cur.fetchone()
        return row[0] if row else default
    finally:
        conn.close()


# ============================================================
# Storage helpers
# ============================================================

def upload_to_storage(bucket: str, filename: str, data: bytes, content_type: str = None) -> Optional[str]:
    """Upload bytes to a storage bucket. Returns public URL or None."""
    sb = get_supabase_client()
    try:
        opts = {"upsert": "true"}
        if content_type:
            opts["content-type"] = content_type
        sb.storage.from_(bucket).upload(path=filename, file=data, file_options=opts)
        return sb.storage.from_(bucket).get_public_url(filename)
    except Exception as e:
        print(f"Upload to {bucket}/{filename} failed: {e}")
        return None


def get_pdf_public_url(filename: str) -> str:
    """Build the public URL for a PDF in storage (without uploading)."""
    return f"{CONFIG['SUPABASE_URL']}/storage/v1/object/public/{CONFIG['BUCKET_PDFS']}/{filename}"


def get_html_public_url(filename: str) -> str:
    """Build the public URL for an HTML in storage."""
    return f"{CONFIG['SUPABASE_URL']}/storage/v1/object/public/{CONFIG['BUCKET_AUDITS']}/{filename}"


def get_csv_public_url(filename: str) -> str:
    """Build the public URL for a CSV in storage."""
    return f"{CONFIG['SUPABASE_URL']}/storage/v1/object/public/{CONFIG['BUCKET_CSVS']}/{filename}"


# ============================================================
# Audit log
# ============================================================

def log_action(action: str, entity_type: str = None, entity_id: int = None,
               details: Dict = None, performed_by: str = 'system'):
    """Insert into audit_logs."""
    conn = get_pg_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO audit_logs (action, entity_type, entity_id, details, performed_by)
            VALUES (%s, %s, %s, %s, %s)
        """, (action, entity_type, entity_id, json.dumps(details) if details else None, performed_by))
        conn.commit()
    except Exception as e:
        print(f"Audit log failed: {e}")
    finally:
        conn.close()


# ============================================================
# Heal database (auto-fill missing stationing / activity_detail)
# ============================================================

def heal_database():
    """Auto-fill missing stationing and activity_detail fields."""
    conn = get_pg_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""SELECT id, location, detailed_levels, category, sub_category,
                              stationing, activity_detail, report_date
                       FROM master_registry
                       WHERE stationing IS NULL OR TRIM(stationing) = ''
                          OR activity_detail IS NULL OR TRIM(activity_detail) = ''""")
        rows = cur.fetchall()

        for row in rows:
            updates = {}
            # Heal stationing
            if not row.get('stationing') or not str(row['stationing']).strip():
                location = row.get('location', '') or ''
                m = re.search(r'(\d+\+\d+\s*(?:to|-|–)\s*\d+\+\d+)', str(location))
                if m:
                    updates['stationing'] = m.group(1)
                elif row.get('detailed_levels'):
                    try:
                        levels = row['detailed_levels']
                        if isinstance(levels, str):
                            levels = json.loads(levels)
                        if levels and isinstance(levels, list):
                            chainages = []
                            for pt in levels:
                                ch = pt.get('chainage') or pt.get('point_id') or pt.get('point_location') or pt.get('station')
                                if ch and '+' in str(ch):
                                    chainages.append(str(ch).strip())
                            if chainages:
                                if len(chainages) == 1 or chainages[0] == chainages[-1]:
                                    updates['stationing'] = chainages[0]
                                else:
                                    updates['stationing'] = f"{chainages[0]} to {chainages[-1]}"
                    except Exception:
                        pass

            # Heal activity_detail
            if not row.get('activity_detail') or not str(row['activity_detail']).strip():
                sub = row.get('sub_category', '') or ''
                cat = row.get('category', '') or ''
                if 'Road' in cat:
                    updates['activity_detail'] = f"- {sub} Level Audit & Handover\n- Verified points/stations\n- Design vs As-Built deviation check within tolerance"
                elif 'Water' in cat or 'Irrigation' in sub:
                    updates['activity_detail'] = f"- {sub} pipe laying & depth audit\n- Invert level compliance check\n- HPC surveyor reference readings checked"
                elif 'Dry' in cat or 'Telecom' in sub:
                    updates['activity_detail'] = f"- {sub} trench excavation and conduits laying\n- Encasement and warning tape levels check"
                elif 'Civil' in cat:
                    updates['activity_detail'] = f"- {sub} inspection and structural audit\n- Levels and alignment verified"
                elif 'Drainage' in cat or 'Storm' in cat:
                    updates['activity_detail'] = f"- {sub} pipeline installation & invert level audit"
                elif 'Landscape' in cat:
                    updates['activity_detail'] = f"- {sub} excavation and formation audit"
                else:
                    updates['activity_detail'] = f"- {sub} inspection and audit\n- Verified\n- Pass"

            if updates:
                set_clauses = ', '.join(f"{k} = %s" for k in updates)
                values = list(updates.values()) + [row['id']]
                cur.execute(f"UPDATE master_registry SET {set_clauses} WHERE id = %s", values)

        conn.commit()
        return len(rows)
    finally:
        conn.close()


# ============================================================
# Category matching (preserved from original)
# ============================================================

def match_category_index(cat_str: str) -> int:
    if not cat_str:
        return 0
    s = str(cat_str).lower().strip()
    if 'road' in s or 'earth' in s:
        return 0
    elif 'water' in s or 'wet' in s or 'irrigation' in s:
        return 1
    elif 'dry' in s or 'elect' in s or 'telecom' in s or 'security' in s:
        return 2
    elif 'struct' in s or 'cross' in s or 'civil' in s:
        return 3
    return 0
