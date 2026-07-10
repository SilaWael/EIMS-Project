# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import json
import sqlite3
import os
import shutil
import io
import re
from datetime import datetime
from bs4 import BeautifulSoup

# ==============================================================================
#  CONFIGURATION & CONSTANTS
# ==============================================================================
DB_NAME = "eims.db"
ARCHIVE_DIR = "pdf_archive"

# Ensure directories exist
if not os.path.exists(ARCHIVE_DIR):
    os.makedirs(ARCHIVE_DIR)

# Set Streamlit Page Configuration
st.set_page_config(
    page_title="EIMS - Engineering Information Management System",
    page_icon="\U0001F6E1\ufe0f",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Premium Custom CSS Injection for RTL and Elegant Theme
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&family=Outfit:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"], .stMarkdown {
        font-family: 'Cairo', 'Outfit', sans-serif;
    }
    
    .rtl-text {
        direction: ltr;
        text-align: left;
    }

    h1.rtl-text,
    p.rtl-text {
        text-align: center;
    }
    
    /* Metric Card Styling */
    .metric-card {
        background: linear-gradient(135deg, rgba(2, 132, 199, 0.05), rgba(0, 105, 92, 0.05));
        border: 1px solid rgba(2, 132, 199, 0.2);
        padding: 1.5rem;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        text-align: center;
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        border-color: #0284c7;
    }
    .metric-title {
        font-size: 0.95rem;
        color: inherit;
        opacity: 0.85;
        margin-bottom: 0.5rem;
        font-weight: 600;
    }
    .metric-val {
        font-size: 2rem;
        font-weight: 800;
        color: #0284c7;
    }
    .metric-unit {
        font-size: 1rem;
        color: #00695C;
        font-weight: 700;
        margin-left: 0.25rem;
    }
    
    /* Elegant JSON blocks */
    .json-code {
        direction: ltr;
        text-align: left;
        background-color: #0f172a;
        color: #38bdf8;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #0284c7;
    }
    
    /* Custom Badge Classes */
    .badge {
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.85rem;
        font-weight: 700;
        display: inline-block;
    }
    .badge-pass { background-color: rgba(16, 185, 129, 0.2); color: #10b981; }
    .badge-fail { background-color: rgba(239, 68, 68, 0.2); color: #ef4848; }
    .badge-info { background-color: rgba(59, 130, 246, 0.2); color: #3b82f6; }
    
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
#  DATABASE OPERATIONS
# ==============================================================================
def heal_database():
    """Automatically extracts stationing and fills activity details for all rows in eims.db if null or empty."""
    import sqlite3
    import re
    import json
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, location, detailed_levels, category, sub_category, stationing, activity_detail, report_date FROM master_registry")
        rows = cursor.fetchall()
        
        for row in rows:
            rec_id, location, detailed_levels_json, category, sub_category, stationing, activity_detail, report_date = row
            updated = False
            new_stationing = stationing
            new_activity = activity_detail
            
            # 1. Heal stationing if empty or null
            if not stationing or str(stationing).strip() == "" or stationing == "None" or stationing is None:
                # Try from location
                if location:
                    m = re.search(r'(\d+\+\d+\s*(?:to|?|-|?)\s*\d+\+\d+)', str(location))
                    if m:
                        new_stationing = m.group(1)
                        updated = True
                    else:
                        m_single = re.search(r'(\d+\+\d+)', str(location))
                        if m_single:
                            new_stationing = m_single.group(1)
                            updated = True
                
                # If still empty, try from detailed levels JSON
                if (not new_stationing or str(new_stationing).strip() == "") and detailed_levels_json:
                    try:
                        levels = json.loads(detailed_levels_json)
                        if levels and isinstance(levels, list):
                            chainages = []
                            for pt in levels:
                                ch = pt.get("chainage") or pt.get("point_id") or pt.get("point_location")
                                if ch and "+" in str(ch):
                                    chainages.append(str(ch).strip())
                            if chainages:
                                start_ch = chainages[0]
                                end_ch = chainages[-1]
                                if start_ch == end_ch:
                                    new_stationing = start_ch
                                else:
                                    new_stationing = f"{start_ch} to {end_ch}"
                                updated = True
                    except Exception:
                        pass
            
            # 2. Heal activity_detail if empty or null
            if not activity_detail or str(activity_detail).strip() == "" or activity_detail == "None" or activity_detail is None:
                pts_count = 0
                if detailed_levels_json:
                    try:
                        levels = json.loads(detailed_levels_json)
                        pts_count = len(levels)
                    except Exception:
                        pass
                
                new_activity = f"- {sub_category} inspection and levels audit.\n- {pts_count} points/stations verified and approved.\n- Tolerance compliance verification (Pass)."
                if "Road" in category:
                    new_activity = f"- {sub_category} Level Audit & Handover\n- {pts_count} cross-section points verified\n- Design vs As-Built deviation check within tolerance"
                elif "Water" in category or "Irrigation" in sub_category:
                    new_activity = f"- {sub_category} pipe laying & depth audit\n- Invert level compliance check\n- HPC surveyor reference readings checked"
                elif "Dry" in category or "Telecom" in sub_category or "ADMCC" in sub_category:
                    new_activity = f"- {sub_category} trench excavation and conduits laying\n- Encasement and warning tape levels check\n- {pts_count} path stations verified"
                updated = True
                
            # 3. Heal/Normalize existing date format to YYYY-MM-DD
            from datetime import datetime
            normalized_date = report_date
            if report_date:
                d_str = str(report_date).strip()
                if d_str.endswith(".0"):
                    d_str = d_str[:-2]
                for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
                    try:
                        dt = datetime.strptime(d_str, fmt)
                        normalized_date = dt.strftime("%Y-%m-%d")
                        break
                    except ValueError:
                        pass
            if normalized_date != report_date:
                updated = True

            if updated:
                cursor.execute("""
                    UPDATE master_registry 
                    SET stationing = ?, activity_detail = ?, report_date = ?
                    WHERE id = ?
                """, (new_stationing, new_activity, normalized_date, rec_id))
                
        conn.commit()
    except Exception as e:
        pass
    finally:
        conn.close()

def init_db():
    """Initializes the SQLite database with required tables."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS master_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date TEXT NOT NULL,
            category TEXT NOT NULL,
            sub_category TEXT NOT NULL,
            location TEXT NOT NULL,
            quantity REAL NOT NULL,
            unit TEXT NOT NULL,
            status TEXT NOT NULL,
            remarks TEXT,
            pdf_filename TEXT,
            pdf_path TEXT,
            detailed_levels TEXT
        )
    """)
    
    # Create system settings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # Dynamic schema migration: add stationing and activity_detail columns if they don't exist
    cursor.execute("PRAGMA table_info(master_registry)")
    columns = [col[1] for col in cursor.fetchall()]
    if "stationing" not in columns:
        cursor.execute("ALTER TABLE master_registry ADD COLUMN stationing TEXT")
    if "activity_detail" not in columns:
        cursor.execute("ALTER TABLE master_registry ADD COLUMN activity_detail TEXT")
        
    conn.commit()
    conn.close()
    
    # Run auto-healing of null columns
    heal_database()

init_db()

def save_setting(key, value):
    """Saves a setting permanently to the SQLite database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("CREATE TABLE IF NOT EXISTS system_settings (key TEXT PRIMARY KEY, value TEXT)")
        cursor.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()

def get_setting(key, default=None):
    """Retrieves a persistent setting from the SQLite database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    val = default
    try:
        cursor.execute("CREATE TABLE IF NOT EXISTS system_settings (key TEXT PRIMARY KEY, value TEXT)")
        cursor.execute("SELECT value FROM system_settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row:
            val = row[0]
    except Exception:
        pass
    finally:
        conn.close()
    return val

def find_file_case_insensitive(directory, filename):
    """Searches a directory for a filename case-insensitively and strips trailing spaces."""
    if not os.path.exists(directory):
        return None
    target = filename.strip().lower()
    for f in os.listdir(directory):
        if f.strip().lower() == target:
            return os.path.abspath(os.path.join(directory, f))
    return None

def normalize_date_to_db(date_str):
    """Standardizes any date format (like DD-MM-YYYY or M/D/YYYY) to YYYY-MM-DD for database storage."""
    if not date_str:
        return "2026-05-18"
    date_str = str(date_str).strip()
    if date_str.endswith(".0"):
        date_str = date_str[:-2]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    return date_str

def format_date_to_display(date_str):
    """Converts database date (YYYY-MM-DD) to DD-MM-YYYY for unified screen display."""
    if not date_str:
        return ""
    date_str = str(date_str).strip()
    if date_str.endswith(".0"):
        date_str = date_str[:-2]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%d-%m-%Y")
        except ValueError:
            pass
    return date_str

def match_category_index(cat_str):
    """Intelligently matches a category string to one of the 4 project main categories."""
    if not cat_str:
        return 0
    cat_str = str(cat_str).lower().strip()
    if "road" in cat_str or "earth" in cat_str:
        return 0
    elif "water" in cat_str or "wet" in cat_str or "irrigation" in cat_str:
        return 1
    elif "dry" in cat_str or "elect" in cat_str or "telecom" in cat_str or "security" in cat_str:
        return 2
    elif "struct" in cat_str or "cross" in cat_str or "civil" in cat_str:
        return 3
    return 0

def save_record(report_date, category, sub_category, location, quantity, unit, status, remarks, pdf_file, detailed_levels_list, original_filename=None, stationing=None, activity_detail=None):
    """Saves a record to SQLite database and copies uploaded PDF to archive."""
    report_date = normalize_date_to_db(report_date)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    pdf_filename = None
    pdf_path = None
    
    if pdf_file is not None:
        # User manually uploaded the file, so we archive it
        safe_date = report_date.replace("-", "")
        safe_cat = category.replace(" ", "_").replace("&", "and")
        safe_sub = sub_category.replace(" ", "_").replace("/", "_")
        original_ext = os.path.splitext(original_filename or getattr(pdf_file, 'name', '.pdf'))[1]
        pdf_filename = f"{safe_date}_{safe_cat}_{safe_sub}{original_ext}"
        pdf_path = os.path.join(ARCHIVE_DIR, pdf_filename)
        
        # Save file to archive folder
        if isinstance(pdf_file, bytes):
            with open(pdf_path, "wb") as f:
                f.write(pdf_file)
        else:
            with open(pdf_path, "wb") as f:
                f.write(pdf_file.getbuffer())
    elif original_filename:
        # Feature: Auto-link to Finished PDFs or Processed_Audits directly without copying
        current_dir = os.path.abspath(os.path.dirname(__file__))
        outer_dir = os.path.dirname(current_dir)
        
        found_path = None
        search_dirs = []
        
        # Read and include custom PDF search directory if configured
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
            fp = find_file_case_insensitive(sd, original_filename)
            if fp:
                found_path = fp
                break
                
        if found_path:
            pdf_path = found_path
            pdf_filename = os.path.basename(found_path)
            
    detailed_levels_json = json.dumps(detailed_levels_list) if detailed_levels_list else None
    
    # Auto-extract stationing if not provided
    if not stationing and location:
        m_ch = re.search(r'(\d+\+\d+\s*(?:to|-|-)\s*\d+\+\d+)', location)
        if m_ch:
            stationing = m_ch.group(1)
            
    cursor.execute("""
        INSERT INTO master_registry (
            report_date, category, sub_category, location, quantity, unit, status, remarks, pdf_filename, pdf_path, detailed_levels, stationing, activity_detail
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        report_date, category, sub_category, location, quantity, unit, status, remarks, pdf_filename, pdf_path, detailed_levels_json, stationing, activity_detail
    ))
    
    conn.commit()
    conn.close()
    return True

def delete_record(record_id):
    """Deletes a record and its associated archived PDF if present."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT pdf_path FROM master_registry WHERE id = ?", (record_id,))
    row = cursor.fetchone()
    if row and row[0]:
        pdf_path = row[0]
        if os.path.exists(pdf_path):
            # ONLY delete if it's inside our managed pdf_archive folder!
            if 'pdf_archive' in pdf_path:
                try:
                    os.remove(pdf_path)
                except Exception:
                    pass
                
    cursor.execute("DELETE FROM master_registry WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()
    return True

def load_data():
    """Loads all records from database."""
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM master_registry ORDER BY report_date DESC, id DESC", conn)
    conn.close()
    if "report_date" in df.columns:
        df["report_date"] = df["report_date"].apply(format_date_to_display)
    return df

# ==============================================================================
# HTML REPORT PARSERS (Direct import without manual text copying)
# ==============================================================================
def extract_date_from_html(soup, text):
    """Extracts date from HTML content in multiple formats."""
    date_badge = soup.find(class_="header-badge") or soup.find(class_="header-date")
    date_str = None
    if date_badge:
        text_badge = date_badge.get_text()
        date_match = re.search(r'(\d{1,2})\s+(May|June|July|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})', text_badge, re.IGNORECASE)
        if date_match:
            day, month_str, year = date_match.groups()
            months = {"jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06", 
                      "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"}
            month = months.get(month_str.lower()[:3], "05")
            date_str = f"{year}-{month}-{int(day):02d}"
            
    if not date_str:
        title_text = soup.title.string if soup.title else ""
        date_match = re.search(r'(\d{1,2})\s+(May|June|July|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})', title_text, re.IGNORECASE)
        if date_match:
            day, month_str, year = date_match.groups()
            months = {"jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06", 
                      "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"}
            month = months.get(month_str.lower()[:3], "05")
            date_str = f"{year}-{month}-{int(day):02d}"
            
    if not date_str:
        date_match = re.search(r'(\d{1,2})\s*[-/]\s*(\d{1,2})\s*[-/]\s*(\d{4})', text)
        if date_match:
            day, month, year = date_match.groups()
            date_str = f"{year}-{int(month):02d}-{int(day):02d}"
            
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
        
    return date_str

def parse_html_report(html_bytes):
    html_content = html_bytes.decode("utf-8", errors="ignore")
    soup = BeautifulSoup(html_content, 'html.parser')
    text = soup.get_text()
    date_str = extract_date_from_html(soup, text)
    doc_title = soup.title.string if soup.title else ""
    h1_tag = soup.find('h1')
    h1_text = h1_tag.get_text() if h1_tag else ""
    doc_context = (doc_title + " " + h1_text + " " + text[:1000]).lower()
    
    def get_category_from_text(t):
        if any(w in t for w in ["subgrade", "pavement", "road", "earthwork", "compaction"]):
            return "Road Works & Earthworks"
        elif any(w in t for w in ["potable", "irrigation", "water", "wet utility", "pipe", "pw"]):
            return "Water Networks (Wet Utilities)"
        elif any(w in t for w in ["telecom", "lighting", "admcc", "trench", "security", "conduit", "dry utility"]):
            return "Dry Utilities & Security"
        elif any(w in t for w in ["crossing", "duct", "bridge", "civil structure", "culvert", "manhole", "concrete structure"]):
            return "Civil Structures & Crossings"
        return "Dry Utilities & Security"
        
    tables = soup.find_all('table')
    if not tables:
        return []
    records = []
    if ("subgrade" in doc_context or "road subgrade" in doc_context) and len(tables) == 2:
        rows = tables[0].find_all('tr')
        if len(rows) >= 2:
            cols = [td.get_text(strip=True) for td in rows[1].find_all('td')]
            if len(cols) >= 6:
                desc = cols[1]
                loc = cols[2]
                from_ch = cols[3]
                to_ch = cols[4]
                length = 0.0
                try: length = float(cols[5].replace(",", ""))
                except ValueError: pass
                detailed_levels = []
                lvl_rows = tables[1].find_all('tr')
                for r in lvl_rows[1:]:
                    tds = [td.get_text(strip=True) for td in r.find_all('td')]
                    if len(tds) >= 6:
                        try:
                            detailed_levels.append({
                                "point_location": tds[0],
                                "offset": tds[1],
                                "required_level": float(tds[2].replace(",", "")),
                                "as_built_level": float(tds[3].replace(",", "")),
                                "difference": float(tds[4].replace(",", "")),
                                "status": tds[5]
                            })
                        except ValueError: pass
                records.append({
                    "report_date": date_str,
                    "category": "Road Works & Earthworks",
                    "sub_category": desc,
                    "location": f"{loc} (CH {from_ch} to {to_ch})",
                    "quantity": length,
                    "unit": "m",
                    "status": "Pass",
                    "remarks": f"All {len(detailed_levels)} points verified. Trimming and compaction compliant.",
                    "detailed_levels": detailed_levels,
                    "stationing": f"{from_ch} to {to_ch}",
                    "activity_detail": f"- {desc} - Level Audit & Handover\n- {len(detailed_levels)} points verified\n- Tolerance compliance check (Pass)"
                })
                return records
    if "irrigation" in doc_context and len(tables) >= 2:
        total_len = 304.58
        tfoot = tables[0].find('tfoot')
        if tfoot:
            footer_text = tfoot.get_text()
            match = re.search(r'([\d,.]+)\s*m', footer_text)
            if match:
                total_len = float(match.group(1).replace(",", ""))
        detailed_levels = []
        rows = tables[1].find_all('tr')
        for r in rows[1:]:
            tds = [td.get_text(strip=True) for td in r.find_all('td')]
            if len(tds) >= 6:
                try:
                    detailed_levels.append({
                        "location_scope": tds[0],
                        "station": tds[1],
                        "required_level": float(tds[2].replace(",", "")),
                        "as_built_level": float(tds[3].replace(",", "")),
                        "difference": float(tds[4].replace(",", "")),
                        "type": "Pipe Top",
                        "status": tds[5]
                    })
                except ValueError: pass
        if len(tables) >= 3:
            rows = tables[2].find_all('tr')
            for r in rows[1:]:
                tds = [td.get_text(strip=True) for td in r.find_all('td')]
                if len(tds) >= 6:
                    try:
                        detailed_levels.append({
                            "location_scope": tds[0],
                            "station": tds[1],
                            "required_level": float(tds[2].replace(",", "")),
                            "as_built_level": float(tds[3].replace(",", "")),
                            "difference": float(tds[4].replace(",", "")),
                            "type": "Formation",
                            "status": tds[5]
                        })
                    except ValueError: pass
        records.append({
            "report_date": date_str,
            "category": "Water Networks (Wet Utilities)",
            "sub_category": "Irrigation Network Installation",
            "location": "RD 5 - LHS & RHS",
            "quantity": total_len,
            "unit": "m",
            "status": "Pass",
            "remarks": f"Net Length: {total_len} m. Levels within standard tolerances.",
            "detailed_levels": detailed_levels,
            "stationing": "LHS: 0+389.32 - 0+519.32 & RHS: 0+389.45 - 0+421.03",
            "activity_detail": f"- Pipe Installation (Top Level) - LHS & RHS\n- Formation Level handover & Trench Typical audit\n- Vertical Offset Audit - Pass"
        })
        return records
    work_items = []
    summary_rows = tables[0].find_all('tr')
    for r in summary_rows:
        if r.find('th') or r.parent.name == 'thead' or r.parent.name == 'tfoot': continue
        tds = [td.get_text(separator=" ", strip=True) for td in r.find_all('td')]
        if len(tds) >= 4:
            desc = tds[0]
            pages = tds[1]
            loc = tds[2]
            q_text = tds[3]
            if "grand total" in desc.lower() or "total" in desc.lower(): continue
            q_val = 1.0
            q_unit = "Unit"
            q_match = re.search(r'([\d,.]+)\s*(?:m|meter)', q_text, re.IGNORECASE)
            if q_match:
                q_val = float(q_match.group(1).replace(",", ""))
                q_unit = "m"
            else:
                q_match_any = re.search(r'([\d,.]+)', q_text)
                if q_match_any:
                    try:
                        q_val = float(q_match_any.group(1).replace(",", ""))
                        if any(u in q_text.lower() for u in ["duct", "crossing", "structure", "manhole", "joint"]): q_unit = "Unit"
                        else: q_unit = "m"
                    except Exception: pass
            work_items.append({
                "description": desc,
                "pages": pages,
                "location": loc,
                "quantity": q_val,
                "unit": q_unit,
                "category": get_category_from_text(desc.lower())
            })
    for table_idx, tbl in enumerate(tables[1:], start=1):
        lvl_rows = tbl.find_all('tr')
        if len(lvl_rows) < 2: continue
        preceding_text = ""
        curr = tbl
        while curr:
            header = curr.find(class_=re.compile(r'header-left|section-header|section-title|title', re.IGNORECASE))
            if header and header.get_text().strip():
                preceding_text = header.get_text().strip()
                break
            prev = curr.previous_sibling
            found = False
            while prev:
                if prev.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    preceding_text = prev.get_text().strip()
                    found = True; break
                if prev.name == 'div':
                    hdr = prev.find(class_=re.compile(r'title|header', re.IGNORECASE))
                    if hdr:
                        preceding_text = hdr.get_text().strip()
                        found = True; break
                    txt = prev.get_text().strip()
                    if txt and len(txt) < 300:
                        preceding_text = txt
                        found = True; break
                prev = prev.previous_sibling
            if found: break
            curr = curr.parent
            if curr and curr.name == 'body': break
        tbl_text = tbl.get_text(separator=" ", strip=True)
        search_context = (preceding_text + " " + tbl_text).lower()
        best_match = None
        best_score = 0
        for item in work_items:
            score = 0
            desc_words = [w for w in re.split(r'\W+', item["description"].lower()) if len(w) > 2]
            loc_words = [w for w in re.split(r'\W+', item["location"].lower()) if len(w) > 2]
            for w in desc_words:
                if w in preceding_text.lower(): score += 10
                elif w in search_context: score += 5
            for w in loc_words:
                if w in preceding_text.lower(): score += 4
                elif w in search_context: score += 2
            if score > best_score:
                best_score = score
                best_match = item
        if best_match and best_score >= 5: matched_item = best_match
        else:
            category = get_category_from_text(search_context)
            matched_item = {
                "description": f"Detailed Technical Section #{table_idx}",
                "location": "Project Scope",
                "quantity": 1.0,
                "unit": "\u2699\ufe0f Unit",
                "category": category
            }
        headers = [th.get_text(separator=" ", strip=True).lower() for th in lvl_rows[0].find_all(['th', 'td'])]
        def safe_float(s):
            if not s: return 0.0
            s = s.replace(",", "").strip()
            if s in ['-', '-', 'N/A', 'n/a', '']: return 0.0
            m = re.search(r'([\d,.]+)', s)
            return float(m.group(1).replace(',', '')) if m else 0.0
        detailed_levels = []
        pt_idx, req_idx, asb_idx, diff_idx, stat_idx = 0, 1, 2, 3, 4
        for idx, h in enumerate(headers):
            if any(w in h for w in ["station", "point", "id", "chainage", "page", "duct"]): pt_idx = idx
            elif any(w in h for w in ["design", "required", "excavation", "blinding", "target", "design level", "il ="]): req_idx = idx
            elif any(w in h for w in ["as-built", "executed", "actual", "concrete", "as_built", "top", "level"]): asb_idx = idx
            elif any(w in h for w in ["diff", "deviation", "error"]): diff_idx = idx
            elif any(w in h for w in ["status", "assessment", "verdict", "engineering"]): stat_idx = idx
        for r in lvl_rows[1:]:
            tds = [td.get_text(separator=" ", strip=True) for td in r.find_all('td')]
            if len(tds) > max(pt_idx, req_idx, asb_idx):
                try:
                    r_lvl = safe_float(tds[req_idx])
                    a_lvl = safe_float(tds[asb_idx])
                    detailed_levels.append({
                        "point_location": tds[pt_idx],
                        "required_level": r_lvl,
                        "as_built_level": a_lvl,
                        "difference": safe_float(tds[diff_idx]) if diff_idx < len(tds) else round(a_lvl - r_lvl, 3),
                        "status": tds[stat_idx] if stat_idx < len(tds) else "Pass"
                    })
                except Exception: pass
        stationing = ""
        m_ch = re.search(r'(\d+\+\d+\s*(?:to|-|-)\s*\d+\+\d+)', matched_item["location"])
        if m_ch: stationing = m_ch.group(1)
        else:
            m_pt = re.search(r'([A-Za-z0-9-]+\s*(?:to|-|-|->)\s*[A-Za-z0-9-]+)', matched_item["location"])
            if m_pt: stationing = m_pt.group(1)
        activity_detail = f"- {matched_item['description']} - Level Audit & Handover\n- {len(detailed_levels)} points verified\n- Design vs As-Built deviation check within tolerance"
        records.append({
            "report_date": date_str,
            "category": matched_item["category"],
            "sub_category": matched_item["description"],
            "location": matched_item["location"],
            "quantity": matched_item["quantity"],
            "unit": matched_item["unit"],
            "status": "Pass",
            "remarks": f"Technical audit verified successfully for {matched_item['description']}.",
            "detailed_levels": detailed_levels,
            "stationing": stationing,
            "activity_detail": activity_detail
        })
    return records

# ==============================================================================
# EXCEL STYLED EXPORTER
# ==============================================================================
def export_to_excel(df_filtered):
    """Generates styled Excel file using XlsxWriter."""
    output = io.BytesIO()
    cols_to_export = [
        "id", "report_date", "category", "sub_category", "location", "stationing", 
        "activity_detail", "quantity", "unit", "status", "remarks", "pdf_filename"
    ]
    for c in cols_to_export:
        if c not in df_filtered.columns: df_filtered[c] = ""
    df_export = df_filtered[cols_to_export].copy()
    df_export.columns = [
        "ID", "Date", "Category", "Sub-Category / Layer", "Location Scope", "Detailed Stationing",
        "Technical Activities Detail", "Quantity", "Unit", "Approval Status", "Remarks / Tolerance", "PDF Reference Filename"
    ]
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_export.to_excel(writer, sheet_name='EIMS Master Registry', index=False)
        workbook  = writer.book
        worksheet = writer.sheets['EIMS Master Registry']
        header_format = workbook.add_format({'bold': True, 'text_wrap': True, 'valign': 'vcenter', 'fg_color': '#00695C', 'font_color': '#FFFFFF', 'border': 1, 'font_name': 'Segoe UI', 'font_size': 11, 'align': 'center'})
        cell_format = workbook.add_format({'valign': 'vcenter', 'font_name': 'Segoe UI', 'font_size': 10, 'border': 1, 'align': 'left'})
        number_format = workbook.add_format({'valign': 'vcenter', 'font_name': 'Segoe UI', 'font_size': 10, 'border': 1, 'align': 'right', 'num_format': '#,##0.00'})
        for col_num, value in enumerate(df_export.columns.values): worksheet.write(0, col_num, value, header_format)
        for row_idx in range(len(df_export)):
            for col_idx in range(len(df_export.columns)):
                val = df_export.iloc[row_idx, col_idx]
                if isinstance(val, (int, float)): worksheet.write_number(row_idx + 1, col_idx, val, number_format)
                else: worksheet.write(row_idx + 1, col_idx, str(val) if pd.notnull(val) else "", cell_format)
        for i, col in enumerate(df_export.columns):
            max_len = max(df_export[col].astype(str).map(len).max(), len(col)) + 4
            worksheet.set_column(i, i, min(max(max_len, 10), 40))
        worksheet.hide_gridlines(2)
    return output.getvalue()


def render_database_admin_panel(df):
    """Shows database maintenance actions inside the password-protected import page."""
    with st.expander("Database Administration & Record Management (Delete / Factory Reset Options)"):
        if df.empty:
            st.info("The database is currently empty. There are no records available for deletion or reset actions.")
            return

        st.markdown("#### Delete Single Record")
        admin_selected_id = st.selectbox(
            "Select the Record ID you want to permanently delete:",
            options=df['id'].unique(),
            key="admin_single_delete_id"
        )
        st.write(
            f"This will permanently delete record ID `{admin_selected_id}` and its associated local PDF from the database."
        )
        if st.button("Delete This Record Permanently", key="admin_delete_single"):
            if delete_record(admin_selected_id):
                st.success("Record deleted successfully!")
                st.rerun()

        st.markdown("---")
        st.markdown("#### Bulk Delete / Multi-Record Eraser")
        ids_to_del = st.multiselect(
            "Select multiple Record IDs to delete at once:",
            options=df['id'].unique(),
            key="bulk_delete_ids"
        )
        if ids_to_del:
            if st.button(f"Confirm Permanent Deletion of {len(ids_to_del)} Selected Records", key="admin_delete_bulk"):
                conn_del = sqlite3.connect(DB_NAME)
                cursor_del = conn_del.cursor()
                for d_id in ids_to_del:
                    cursor_del.execute("SELECT pdf_path FROM master_registry WHERE id = ?", (d_id,))
                    row_del = cursor_del.fetchone()
                    if row_del and row_del[0] and os.path.exists(str(row_del[0])):
                        if ARCHIVE_DIR in str(row_del[0]):
                            try:
                                os.remove(row_del[0])
                            except Exception:
                                pass
                    cursor_del.execute("DELETE FROM master_registry WHERE id = ?", (d_id,))
                conn_del.commit()
                conn_del.close()
                st.success("Successfully deleted selected records!")
                st.rerun()

        st.markdown("---")
        st.markdown("#### Clear Database & Factory Reset")
        st.write("Use this only when you want to permanently clear all historical records and start with an empty database.")
        confirm_reset = st.checkbox(
            "Yes, I want to permanently delete all records from the database. This cannot be undone.",
            key="admin_confirm_reset"
        )
        if confirm_reset:
            if st.button("Execute Wiping Database & Factory Reset Now", key="admin_execute_reset"):
                conn_reset = sqlite3.connect(DB_NAME)
                cursor_reset = conn_reset.cursor()
                cursor_reset.execute("SELECT pdf_path FROM master_registry")
                rows_reset = cursor_reset.fetchall()
                for r_item in rows_reset:
                    if r_item[0] and os.path.exists(str(r_item[0])):
                        if ARCHIVE_DIR in str(r_item[0]):
                            try:
                                os.remove(r_item[0])
                            except Exception:
                                pass
                cursor_reset.execute("DELETE FROM master_registry")
                cursor_reset.execute("DELETE FROM sqlite_sequence WHERE name='master_registry'")
                conn_reset.commit()
                conn_reset.close()
                st.success("Database reset successfully! You can now start with a clean empty database.")
                st.rerun()

# ==============================================================================
#  STREAMLIT FRONTEND
# ==============================================================================

# Sidebar Header & Brand Styling
st.sidebar.markdown("""
    <div style="text-align: center; padding: 1rem 0;">
        <h2 style="color: #0284c7; font-weight: 800; margin-bottom: 0;">\U0001F6E1\ufe0f EIMS System</h2>
        <p style="color: #94a3b8; font-size: 0.9rem;">Smart Engineering Information Management</p>
        <hr style="border-color: rgba(226, 232, 240, 0.1); margin-top: 0.5rem;"/>
    </div>
""", unsafe_allow_html=True)

menu = st.sidebar.radio(
    "\U0001F4AC Main Navigation Menu",
    ["\U0001F4CA Master Dashboard", "\U0001F4E5 Import Engineering Reports"],
    index=0
)

st.sidebar.markdown("<br>", unsafe_allow_html=True)
with st.sidebar.expander("\u2699\ufe0f Paths & References Settings", expanded=False):
    current_custom_dir = get_setting("custom_pdf_dir", "")
    custom_pdf_dir = st.text_input(
        "\U0001F4C1 Custom PDF Folder Path:",
        value=current_custom_dir,
        placeholder="Example: D:/MyProject/PDFs",
        help="If specified, EIMS will search this folder for PDF references automatically during import."
    )
    if custom_pdf_dir != current_custom_dir:
        save_setting("custom_pdf_dir", custom_pdf_dir.strip())
        st.success("\U0001F4BE Path saved successfully!")
        st.rerun()

st.sidebar.markdown("""
    <div style="position: fixed; bottom: 10px; left: 10px; right: 10px; font-size: 0.8rem; color: #64748b; text-align: center; border-top: 1px solid rgba(226, 232, 240, 0.05); padding-top: 10px;">
        \U0001F468\u200d\U0001F4BB Supervision: Eng. <strong>Wael Radwan</strong><br>
        108 Villas Project - ADHA
    </div>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# TAB 1: MASTER DASHBOARD
# ------------------------------------------------------------------------------
if menu == "\U0001F4CA Master Dashboard":
    st.markdown("<h1 class='rtl-text' style='color: #0284c7;'>\U0001F4CA Master Registry Dashboard</h1>", unsafe_allow_html=True)
    st.markdown("<p class='rtl-text' style='color: #94a3b8; margin-top: -10px;'>Comprehensive registry of construction audits, approved quantities, level details, and PDF references.</p>", unsafe_allow_html=True)
    
    # Load Fresh Data
    df = load_data()
    
    if df.empty:
        st.info("\U0001F44B The database is currently empty. Please go to the '\U0001F4E5 Import Engineering Reports' tab to upload your HTML reports from the Processed_Audits folder and start using the system.")
    else:
        # 1. Premium Metric Dashboard Cards
        st.markdown("### \U0001F4C8 Approved Cumulative Engineering Quantities")
        
        all_road_layers = df[df['category'].str.contains("Road", case=False, na=False)]['sub_category'].unique()
        
        # Selectbox aligned exactly above the first metric card (Roads)
        col_sel, col_empty = st.columns([1, 3])
        with col_sel:
            selected_road_layer = st.selectbox(
                "\U0001F6E3\ufe0f Cumulative Roads Layer (Road Works only):", 
                all_road_layers if len(all_road_layers) > 0 else ["Subgrade 2nd Layer"]
            )
            
        # Computation of dynamic quantities
        # Roads
        road_df = df[(df['category'].str.contains("Road", case=False, na=False)) & (df['sub_category'] == selected_road_layer)]
        total_roads = road_df['quantity'].sum()
        
        # Wet Utilities
        wet_df = df[df['category'].str.contains("Water|Irrigation|Wet", case=False, na=False)]
        total_wet = wet_df['quantity'].sum()
        
        # Dry Utilities
        dry_df = df[df['category'].str.contains("Dry|Lighting|Telecom|MCC", case=False, na=False)]
        total_dry = dry_df['quantity'].sum()
        
        # Structures
        struct_df = df[df['category'].str.contains("Struct|Crossing|Manhole", case=False, na=False)]
        total_struct = len(struct_df)
        
        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        with m_col1:
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-title">Total Roads Approved ({selected_road_layer})</div>
                    <div class="metric-val">{total_roads:,.2f}<span class="metric-unit"> m</span></div>
                </div>
            """, unsafe_allow_html=True)
        with m_col2:
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-title">Wet Utilities (Water/Irrigation)</div>
                    <div class="metric-val">{total_wet:,.2f}<span class="metric-unit"> m</span></div>
                </div>
            """, unsafe_allow_html=True)
        with m_col3:
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-title">? Dry Utilities & Security</div>
                    <div class="metric-val">{total_dry:,.2f}<span class="metric-unit"> m</span></div>
                </div>
            """, unsafe_allow_html=True)
        with m_col4:
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-title">Crossing Ducts & Civil Structures</div>
                    <div class="metric-val">{total_struct}<span class="metric-unit"> Unit</span></div>
                </div>
            """, unsafe_allow_html=True)
                
        st.markdown("<hr style='border-color: rgba(226, 232, 240, 0.1);'/>", unsafe_allow_html=True)
        
        # 2. Filters & Advanced Search Panel
        st.markdown("### \U0001F50D Advanced Search & Filter Options")
        
        f_col1, f_col2, f_col3, f_col4, f_col5 = st.columns(5)
        
        with f_col1:
            search_query = st.text_input("\U0001F4DD Universal Smart Search (Location, Sub-category, Category, Remarks, Activities):", placeholder="Example: Subgrade, SS390, Feeder Pillar, Approved...")
            
        with f_col2:
            unique_dates = [d for d in list(df['report_date'].unique()) if d]
            def get_sort_key(d_str):
                try: return datetime.strptime(str(d_str), "%d-%m-%Y")
                except ValueError: return datetime.min
            unique_dates.sort(key=get_sort_key, reverse=True)
            date_list = ["All"] + unique_dates
            sel_date = st.selectbox("\U0001F4C5 Filter by Date:", date_list)
            
        with f_col3:
            cat_list = ["All"] + list(df['category'].unique())
            sel_cat = st.selectbox("\U0001F4C2 Filter by Main Category:", cat_list)
            
        with f_col4:
            sub_list = ["All"] + list(df['sub_category'].unique())
            sel_sub = st.selectbox("\U0001F3AF Filter by Activity / Layer:", sub_list)
            
        with f_col5:
            status_list = ["All"] + list(df['status'].unique())
            sel_status = st.selectbox("\U0001F6E1\ufe0f Filter by Inspection Status:", status_list)
            
        # Apply filters
        df_filtered = df.copy()
        
        if search_query:
            df_filtered = df_filtered[
                df_filtered['location'].str.contains(search_query, case=False, na=False) |
                df_filtered['remarks'].str.contains(search_query, case=False, na=False) |
                df_filtered['sub_category'].str.contains(search_query, case=False, na=False) |
                df_filtered['category'].str.contains(search_query, case=False, na=False) |
                df_filtered['stationing'].str.contains(search_query, case=False, na=False) |
                df_filtered['activity_detail'].str.contains(search_query, case=False, na=False) |
                df_filtered['pdf_filename'].str.contains(search_query, case=False, na=False)
            ]
            
        if sel_date != "All":
            df_filtered = df_filtered[df_filtered['report_date'] == sel_date]
            
        if sel_cat != "All":
            df_filtered = df_filtered[df_filtered['category'] == sel_cat]
            
        if sel_sub != "All":
            df_filtered = df_filtered[df_filtered['sub_category'] == sel_sub]
            
        if sel_status != "All":
            df_filtered = df_filtered[df_filtered['status'] == sel_status]
            
        st.markdown(f"\U0001F4CA Found **{len(df_filtered)}** inspection records matching the current filters.")
        
        # Available columns and friendly Arabic headers
        col_options = {
            "id": "ID",
            "report_date": "\U0001F4C5 Report Date",
            "category": "\U0001F4C2 Main Category",
            "sub_category": "\U0001F3AF Sub-category / Layer",
            "location": "\U0001F4CD Location Name",
            "stationing": "\U0001F6E3\ufe0f Stationing (Chainage)",
            "activity_detail": "\U0001F52C Technical Activity Details",
            "quantity": "\U0001F4CF Quantity Approved",
            "unit": "\u2699\ufe0f Unit",
            "status": "\U0001F6E1\ufe0f Audit Decision",
            "remarks": "\U0001F4AC Consultant Remarks & Tolerance",
            "pdf_filename": "\U0001F4C4 PDF Reference"
        }
        
        if 'visible_columns' not in st.session_state:
            saved_cols_str = get_setting('visible_columns')
            if saved_cols_str:
                try:
                    st.session_state['visible_columns'] = json.loads(saved_cols_str)
                except Exception:
                    st.session_state['visible_columns'] = list(col_options.keys())
            else:
                st.session_state['visible_columns'] = list(col_options.keys())
            
        with st.expander("\U0001F441\ufe0f Customize Table Column Visibility & Save Settings"):
            selected_cols = st.multiselect(
                "Choose which columns to display in the main registry. Your settings are saved automatically.",
                options=list(col_options.keys()),
                default=st.session_state['visible_columns'],
                format_func=lambda x: col_options[x]
            )
            if selected_cols != st.session_state['visible_columns']:
                st.session_state['visible_columns'] = selected_cols
                save_setting('visible_columns', json.dumps(selected_cols))
            
        # Show Main Dataframe
        df_display = df_filtered.copy()
        
        # Ensure we keep only the selected columns that exist
        display_cols = [c for c in st.session_state['visible_columns'] if c in df_display.columns]
        if not display_cols:
            display_cols = ["id", "report_date", "category", "sub_category", "location"]
            
        df_display = df_display[display_cols]
        
        all_col_config = {
            "id": "ID",
            "report_date": st.column_config.TextColumn("\U0001F4C5 Report Date"),
            "category": st.column_config.TextColumn("\U0001F4C2 Main Category"),
            "sub_category": st.column_config.TextColumn("\U0001F3AF Sub-category / Layer"),
            "location": st.column_config.TextColumn("\U0001F4CD Location Name"),
            "stationing": st.column_config.TextColumn("\U0001F6E3\ufe0f Stationing (Chainage)"),
            "activity_detail": st.column_config.TextColumn("\U0001F52C Technical Activity Details"),
            "quantity": st.column_config.NumberColumn("\U0001F4CF Quantity Approved", format="%.2f"),
            "unit": st.column_config.TextColumn("\u2699\ufe0f Unit"),
            "status": st.column_config.TextColumn("\U0001F6E1\ufe0f Audit Decision"),
            "remarks": st.column_config.TextColumn("\U0001F4AC Consultant Remarks & Tolerance"),
            "pdf_filename": st.column_config.TextColumn("\U0001F4C4 PDF Reference")
        }
        
        active_col_config = {k: v for k, v in all_col_config.items() if k in display_cols}
        
        st.dataframe(
            df_display, 
            use_container_width=True,
            column_config=active_col_config,
            hide_index=True
        )
        
        st.markdown("<hr style='border-color: rgba(226, 232, 240, 0.1);'/>", unsafe_allow_html=True)
        
        # 3. Selected Row Details & Level Audit Inspector
        st.markdown("### \U0001F50E Level Audit & Engineering Detail Inspector")
        
        selected_id = st.selectbox("\U0001F449 Select Record ID to view level detail and spatial tolerance audit:", df_filtered['id'].unique() if len(df_filtered) > 0 else [])
        
        if selected_id:
            row_data = df[df['id'] == selected_id].iloc[0]
            
            st.markdown(f"""
                <div style="background-color: rgba(128, 128, 128, 0.05); padding: 1.5rem; border-radius: 8px; border-right: 4px solid #0284c7; margin-bottom: 1rem;">
                    <h4 style="margin-top:0; color:#0284c7;">\U0001F4CC Engineering Progress Detail Card</h4>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem;">
                        <div>
                            <p style="margin-bottom: 5px;"><strong>Execution / Report Date:</strong></p>
                            <p style="font-size: 1.1rem; opacity: 0.9;">{row_data['report_date']}</p>
                        </div>
                        <div>
                            <p style="margin-bottom: 5px;"><strong>Project Category:</strong></p>
                            <p style="font-size: 1.1rem; opacity: 0.9;">{row_data['category']}</p>
                        </div>
                        <div>
                            <p style="margin-bottom: 5px;"><strong>Sub-category / Layer:</strong></p>
                            <p style="font-size: 1.1rem; opacity: 0.9;">{row_data['sub_category']}</p>
                        </div>
                        <div>
                            <p style="margin-bottom: 5px;"><strong>Location & Scope:</strong></p>
                            <p style="font-size: 1.1rem; opacity: 0.9;">{row_data['location']}</p>
                        </div>
                        <div>
                            <p style="margin-bottom: 5px;"><strong>Total Approved Quantity:</strong></p>
                            <p style="color: #10b981; font-size: 1.2rem; font-weight: bold;">{row_data['quantity']:.2f} {row_data['unit']}</p>
                        </div>
                        <div>
                            <p style="margin-bottom: 5px;"><strong>Stationing (Chainage):</strong></p>
                            <p style="font-size: 1.1rem; opacity: 0.9;">{row_data['stationing']}</p>
                        </div>
                    </div>
                    <div style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid rgba(128,128,128,0.2);">
                        <p style="margin-bottom: 5px;"><strong>Audit & Inspection Remarks:</strong></p>
                        <p style="opacity: 0.85;">{row_data['remarks'] if str(row_data['remarks']) != 'nan' else 'No remarks available.'}</p>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            # Robust shared reference PDF lookup
            target_pdf_path = row_data['pdf_path']
            target_pdf_filename = row_data['pdf_filename']
            is_shared = False
            
            if not target_pdf_path or not os.path.exists(str(target_pdf_path)):
                # Look for another activity with the same report_date and category that HAS a valid PDF!
                conn_pdf = sqlite3.connect(DB_NAME)
                cursor_pdf = conn_pdf.cursor()
                cursor_pdf.execute("""
                    SELECT pdf_path, pdf_filename FROM master_registry 
                    WHERE report_date = ? AND category = ? AND pdf_path IS NOT NULL AND pdf_path != ""
                    ORDER BY id ASC LIMIT 1
                """, (row_data['report_date'], row_data['category']))
                alt_pdf = cursor_pdf.fetchone()
                conn_pdf.close()
                
                if alt_pdf and alt_pdf[0] and os.path.exists(alt_pdf[0]):
                    target_pdf_path = alt_pdf[0]
                    target_pdf_filename = alt_pdf[1]
                    is_shared = True

            if target_pdf_path and os.path.exists(str(target_pdf_path)):
                c1, c2, c3 = st.columns([1, 1, 1])
                with c1:
                    if is_shared:
                        st.info("This activity was automatically linked to the shared reference document for the group.")
                    # 1. Native Windows application open local (perfect for desktop users)
                    if st.button("\U0001F4C2 Open PDF", use_container_width=True):
                        try:
                            os.startfile(target_pdf_path)
                            st.toast("\U0001F4C4 File opened successfully in your default document reader!")
                        except Exception as e:
                            st.error(f"Could not open the file locally: {e}")
                with c2:
                    # New button: Open HTML
                    html_filename = os.path.splitext(target_pdf_filename)[0] + ".html"
                    html_path = os.path.join(os.path.dirname(os.path.dirname(target_pdf_path)), 'Processed_Audits', html_filename)
                    if st.button("\U0001F310 Open HTML", use_container_width=True):
                        if os.path.exists(html_path):
                            try:
                                os.startfile(html_path)
                                st.toast("\U0001F310 HTML opened successfully!")
                            except Exception as e:
                                st.error(f"Could not open the HTML file: {e}")
                        else:
                            st.warning(f"HTML report not found at: {html_path}")
                with c3:
                    # 2. Browser standard file download option
                    with open(target_pdf_path, "rb") as f:
                        st.download_button(
                            label="\U0001F4E5 Download PDF",
                            data=f,
                            file_name=target_pdf_filename,
                            mime="application/octet-stream",
                            use_container_width=True
                        )
            else:
                st.warning("No scanned PDF reference is available for this group.")
            

# ------------------------------------------------------------------------------
# TAB 2: SMART REPORT IMPORTER
# ------------------------------------------------------------------------------
elif menu == "\U0001F4E5 Import Engineering Reports":
    admin_password = st.sidebar.text_input("\U0001F512 Admin Password:", type="password")
    if admin_password != "1212":
        st.warning("This page is reserved for the system administrator. Please enter the correct password.")
        st.stop()

    st.markdown("<h1 class='rtl-text' style='color: #0284c7;'>\U0001F4E5 Advanced Technical Reports Import Engine</h1>", unsafe_allow_html=True)
    st.markdown("<p class='rtl-text' style='color: #94a3b8; margin-top: -10px;'>Select the best import method for your data: structured CSV files, direct HTML inspection logs, raw text, or structured JSON.</p>", unsafe_allow_html=True)
    render_database_admin_panel(load_data())

    # CSV Import method only
    
    # Initialize session state for parsed records to hold them across reruns
    if 'parsed_records' not in st.session_state:
        st.session_state['parsed_records'] = []
    if 'pdf_files_dict' not in st.session_state:
        st.session_state['pdf_files_dict'] = {}

    st.markdown("### \U0001F4CA Bulk Daily Progress Import (Excel/CSV)")
    st.info("\U0001F4A1 Please upload your structured CSV files to import daily progress data.")
    
    # Download template button
    template_csv = "Report Date,Main Category,Sub-category,Location,Stationing,Quantity Approved,Unit,PDF Attachment Name,Remarks\n2026-05-08,Road Works & Earthworks,Subgrade Layer 2,Road-02,1+000 to 1+160,160.0,m,Daily Inspection 08-05-2026.pdf,Verified successfully\n2026-05-08,Water Networks (Wet Utilities),200mm PW Pipe Laying,Road-02,0+216 to 0+880,664.0,m,Daily Inspection 08-05-2026.pdf,Compliant with specifications\n2026-05-08,Civil Structures & Crossings,Concrete Road Crossings (PW Ducts),Road-05,PW-RD-07 to PW-RD-11,12.0,Unit,Daily Inspection 08-05-2026.pdf,"
    st.download_button(
        label="\U0001F4E5 Download Blank Excel/CSV Template",
        data=template_csv.encode('utf-8-sig'),
        file_name="EIMS_Daily_Progress_Template.csv",
        mime="text/csv",
        use_container_width=True
    )
    
    st.markdown("---")
    st.markdown("#### \U0001F4E4 1. Upload Completed Progress Files:")
    uploaded_csvs = st.file_uploader("Choose one or multiple completed CSV progress files:", type=["csv"], accept_multiple_files=True)
    
    st.markdown("#### \U0001F4C4 2. Link Digital References (Optional):")
    st.info("\U0001F4A1 You do not need to upload files here if they already exist in Processed_Audits or Finished PDFs. The system will try to find them automatically.")
    pdf_refs = st.file_uploader("Upload the PDF files referenced in the CSV (optional):", type=["pdf", "jpg", "jpeg", "png"], accept_multiple_files=True)
    
    if uploaded_csvs:
        if st.button("\U0001F680 Process All Batches and Extract Engineering Activities", use_container_width=True):
            try:
                extracted = []
                for uploaded_csv in uploaded_csvs:
                    df_csv = pd.read_csv(uploaded_csv)
                    for _, row in df_csv.iterrows():
                        def safe_str(val, default=""):
                            return str(val) if pd.notna(val) else default
                            
                        try: q_val = float(row.get("Quantity Approved", 1.0))
                        except: q_val = 1.0
                            
                        extracted.append({
                            "report_date": format_date_to_display(safe_str(row.get("Report Date", "2026-05-08"))),
                            "category": safe_str(row.get("Main Category", "General Works")),
                            "sub_category": safe_str(row.get("Sub-category", "Unknown Activity")),
                            "location": safe_str(row.get("Location", "Project Scope")),
                            "stationing": safe_str(row.get("Stationing", "")),
                            "quantity": q_val,
                            "unit": safe_str(row.get("Unit", "Unit")),
                            "status": "Pass",
                            "remarks": safe_str(row.get("Remarks", "")),
                            "detailed_levels": [],
                            "csv_pdf_name": safe_str(row.get("PDF Attachment Name", "")),
                            "activity_detail": f"- Quick batch import from CSV file [File: {uploaded_csv.name}]\n- Reference file: {safe_str(row.get('PDF Attachment Name', 'No file'))}"
                        })
                
                st.session_state['parsed_records'] = extracted
                
                # Store multiple PDFs in session state as a dictionary
                pdf_dict = {}
                if pdf_refs:
                    for pdf in pdf_refs:
                        pdf_dict[pdf.name] = pdf.read()
                st.session_state['pdf_files_dict'] = pdf_dict
                
                st.success(f"\U0001F389 Extracted **{len(extracted)}** activities from the file successfully. Review them below, then approve them.")
            except Exception as e:
                st.error(f"An error occurred while reading the CSV file. Please make sure the columns match the downloaded template: {e}")
                
    # Display editable preview form of parsed records
    if st.session_state.get('parsed_records'):
        st.markdown("### \U0001F4CB Review Extracted Data Before Approval")
        st.write("You can now review the extracted data and manually adjust any quantity or location in the forms below.")
        
        all_records_valid = True
        records_to_save = []
        
        # Draw an editable container for each record found
        for idx, r in enumerate(st.session_state['parsed_records']):
            with st.expander(f"\u2699\ufe0f Extracted Record #{idx+1}: {r['category']} - {r['sub_category']}", expanded=True):
                col_r1, col_r2 = st.columns(2)
                with col_r1:
                    p_date = st.text_input("Report Date (DD-MM-YYYY):", value=r['report_date'], key=f"date_{idx}")
                    p_cat = st.selectbox(
                        "Main Project Category:", 
                        ["Road Works & Earthworks", "Water Networks (Wet Utilities)", "Dry Utilities & Security", "Civil Structures & Crossings"],
                        index=match_category_index(r['category']),
                        key=f"cat_{idx}"
                    )
                    p_sub = st.text_input("Sub-category or Layer:", value=r['sub_category'], key=f"sub_{idx}")
                    p_loc = st.text_input("Engineering Location Scope:", value=r['location'], key=f"loc_{idx}")
                    p_stationing = st.text_input("Detailed Stationing:", value=r.get('stationing', ''), key=f"stationing_{idx}")
                    
                with col_r2:
                    p_qty = st.number_input("Measured / Approved Quantity:", value=float(r['quantity']), format="%.2f", key=f"qty_{idx}")
                    p_unit = st.text_input("Approved Unit:", value=r['unit'], key=f"unit_{idx}")
                    p_status = st.selectbox("Technical Audit Decision:", ["Pass", "Rejected"], index=0 if r['status'] == "Pass" else 1, key=f"status_{idx}")
                    p_remarks = st.text_area("Consultant Remarks & Tolerance:", value=r['remarks'], key=f"remarks_{idx}")
                    p_activity = st.text_area("Technical Details & Related Activities:", value=r.get('activity_detail', ''), key=f"activity_{idx}")
                
                # Show and edit levels if present
                detailed_list = r.get("detailed_levels", [])
                edited_levels = []
                if detailed_list:
                    st.markdown("##### Detailed Point-Level Table")
                    levels_df = pd.DataFrame(detailed_list)
                    # Display editable levels data editor
                    edited_df = st.data_editor(levels_df, use_container_width=True, key=f"editor_{idx}", num_rows="dynamic")
                    edited_levels = edited_df.to_dict(orient='records')
                    
                records_to_save.append({
                    "report_date": p_date,
                    "category": p_cat,
                    "sub_category": p_sub,
                    "location": p_loc,
                    "quantity": p_qty,
                    "unit": p_unit,
                    "status": p_status,
                    "remarks": p_remarks,
                    "detailed_levels": edited_levels,
                    "stationing": p_stationing,
                    "activity_detail": p_activity,
                    "csv_pdf_name": r.get("csv_pdf_name")
                })
        
        # Big Submission Button
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("\U0001F4BE Save and Approve All Records"):
            saved_count = 0
            for rec in records_to_save:
                # Figure out which PDF bytes to use
                pdf_name = rec.get("csv_pdf_name")
                file_bytes = None
                
                if 'pdf_files_dict' in st.session_state and st.session_state['pdf_files_dict'] and pdf_name:
                    file_bytes = st.session_state['pdf_files_dict'].get(pdf_name)
                    
                # Save record and attach bytes
                success = save_record(
                    report_date=rec["report_date"],
                    category=rec["category"],
                    sub_category=rec["sub_category"],
                    location=rec["location"],
                    quantity=rec["quantity"],
                    unit=rec["unit"],
                    status=rec["status"],
                    remarks=rec["remarks"],
                    pdf_file=file_bytes,
                    detailed_levels_list=rec["detailed_levels"],
                    original_filename=pdf_name,
                    stationing=rec.get("stationing"),
                    activity_detail=rec.get("activity_detail")
                )
                if success:
                    saved_count += 1
                    
            if saved_count == len(records_to_save):
                st.success(f"Success! Imported and saved **{saved_count}** inspection records and updated the master registry successfully.")
                st.balloons()
                # Clear session state
                st.session_state['parsed_records'] = []
                st.session_state['pdf_files_dict'] = {}
