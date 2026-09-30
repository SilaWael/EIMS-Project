# -*- coding: utf-8 -*-
import io
import json
import os
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup

# --- Application folder / project base folder (the software lives on drive D:) ---
APP_DIR  = os.path.abspath(os.path.dirname(__file__))
BASE_DIR = os.path.dirname(APP_DIR)   # D:\My Work\Infra Daily Report

DB_NAME     = os.path.join(APP_DIR, "eims.db")
ARCHIVE_DIR = os.path.join(APP_DIR, "pdf_archive")

# --- Default reference / output directories ---
# These are only DEFAULTS. Real values are stored in the database (system_settings)
# and can be changed at any time from the sidebar -> "Paths & References Settings".
DEFAULT_PDF_DIR  = os.path.join(BASE_DIR, "Finished PDFs")     # scanned PDF inspection reports
DEFAULT_HTML_DIR = os.path.join(BASE_DIR, "Processed_Audits")  # processed HTML audit reports

# Backwards compatible aliases
PDF_DIR  = DEFAULT_PDF_DIR
HTML_DIR = DEFAULT_HTML_DIR

Path(ARCHIVE_DIR).mkdir(parents=True, exist_ok=True)


def _ensure_dir(path):
    try:
        if path:
            Path(path).mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def get_pdf_dir():
    """Currently configured folder that holds the scanned PDF reports."""
    path = get_setting("pdf_dir", "") or DEFAULT_PDF_DIR
    _ensure_dir(path)
    return path


def get_html_dir():
    """Currently configured folder that holds the processed HTML audits."""
    path = get_setting("html_dir", "") or DEFAULT_HTML_DIR
    _ensure_dir(path)
    return path


def get_extra_pdf_dirs():
    """Extra folders (one per line) that are also searched for PDF references."""
    raw = get_setting("extra_pdf_dirs", "") or ""
    return [p.strip() for p in re.split(r"[\r\n;]+", raw) if p.strip()]


def get_pdf_search_dirs():
    """Ordered list of folders searched when resolving a referenced PDF file."""
    candidates = [
        get_pdf_dir(),
        *get_extra_pdf_dirs(),
        get_setting("custom_pdf_dir", ""),
        get_html_dir(),
        os.path.join(APP_DIR, "Finished PDFs"),
        os.path.join(APP_DIR, "pdf_archive"),
        os.path.join(BASE_DIR, "Finished PDFs"),
        os.path.join(BASE_DIR, "Processed_Audits"),
        BASE_DIR,
    ]
    dirs = []
    for d in candidates:
        if d and os.path.isdir(d) and d not in dirs:
            dirs.append(d)
    return dirs

st.set_page_config(
    page_title="EIMS - Engineering Information Management System",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
html, body, [class*="css"], .stMarkdown { font-family: 'Segoe UI', Arial, sans-serif; }
.eims-hero { padding: 1.2rem 1.4rem; border-radius: 16px; border: 1px solid rgba(14,116,144,.20);
    background: linear-gradient(135deg, rgba(14,116,144,.08), rgba(0,105,92,.05)); margin-bottom: 1rem; }
.eims-hero h1 { margin: 0; }
.metric-card { background: linear-gradient(135deg, rgba(14,116,144,.05), rgba(0,105,92,.05));
    border: 1px solid rgba(14,116,144,.18); padding: 1rem; border-radius: 14px; text-align:center; min-height: 120px; }
.metric-title { font-size:.90rem; opacity:.72; font-weight:600; }
.metric-val { font-size:1.8rem; font-weight:800; margin-top:.35rem; }
.metric-note { font-size:.78rem; opacity:.60; margin-top:.2rem; }
.section-note { opacity:.72; margin-top:-.35rem; margin-bottom:.8rem; }
.small-muted { opacity:.65; font-size:.85rem; }
</style>
""", unsafe_allow_html=True)


def db_conn():
    return sqlite3.connect(DB_NAME)


def ensure_schema():
    with db_conn() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS master_registry (
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
            detailed_levels TEXT,
            stationing TEXT,
            activity_detail TEXT
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")
        cols = [r[1] for r in conn.execute("PRAGMA table_info(master_registry)").fetchall()]
        for name, typ in [("stationing", "TEXT"), ("activity_detail", "TEXT")]:
            if name not in cols:
                conn.execute(f"ALTER TABLE master_registry ADD COLUMN {name} {typ}")


def normalize_date(value):
    if value is None or str(value).strip() == "":
        return None
    s = str(value).strip()
    if s.endswith('.0'):
        s = s[:-2]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    try:
        return pd.to_datetime(s).strftime("%Y-%m-%d")
    except Exception:
        return s


def display_date(value):
    d = normalize_date(value)
    if not d:
        return ""
    return datetime.strptime(d, "%Y-%m-%d").strftime("%d-%m-%Y")


def load_data():
    with db_conn() as conn:
        df = pd.read_sql_query("SELECT * FROM master_registry ORDER BY report_date DESC, id DESC", conn)
    if not df.empty:
        df["report_date_db"] = df["report_date"].apply(normalize_date)
        df["report_date"] = df["report_date_db"].apply(display_date)
    return df


def save_setting(key, value):
    with db_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO system_settings(key,value) VALUES(?,?)", (key, str(value)))


def get_setting(key, default=""):
    with db_conn() as conn:
        row = conn.execute("SELECT value FROM system_settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def find_file_case_insensitive(directory, filename):
    """Looks up a file inside a folder ignoring case and trailing spaces."""
    if not directory or not os.path.isdir(directory):
        return None
    target = str(filename).strip().lower()
    for f in os.listdir(directory):
        if f.strip().lower() == target:
            return os.path.abspath(os.path.join(directory, f))
    return None


def resolve_pdf_path(stored_path, filename):
    """Keeps the stored path when it still exists, otherwise finds the file by name
    inside every configured folder (this is what fixes the move to drive D:)."""
    if stored_path and os.path.exists(str(stored_path)):
        return str(stored_path)
    if filename and str(filename).strip() not in ("", "None", "nan"):
        for sd in get_pdf_search_dirs():
            fp = find_file_case_insensitive(sd, str(filename))
            if fp:
                return fp
    return None


def repair_stored_pdf_paths():
    """Rewrites stale pdf_path values so they point into the configured folders.
    Returns (fixed_count, missing_count)."""
    conn = db_conn()
    cursor = conn.cursor()
    rows = cursor.execute("SELECT id, pdf_filename, pdf_path FROM master_registry").fetchall()
    search_dirs = get_pdf_search_dirs()
    fixed = missing = 0
    for rid, fname, old_path in rows:
        if old_path and os.path.exists(str(old_path)):
            continue
        if not fname or str(fname).strip() in ("", "None", "nan"):
            continue
        new_path = None
        for sd in search_dirs:
            new_path = find_file_case_insensitive(sd, str(fname))
            if new_path:
                break
        if new_path:
            if str(new_path) != str(old_path):
                cursor.execute("UPDATE master_registry SET pdf_path = ? WHERE id = ?", (new_path, rid))
                fixed += 1
        else:
            missing += 1
    conn.commit()
    conn.close()
    return fixed, missing


def safe_html(text):
    return (str(text) if text is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def distinct_nonempty(df, col):
    if col not in df.columns:
        return []
    vals = [str(v) for v in df[col].dropna().unique() if str(v).strip()]
    return sorted(vals)


def apply_filters(df, start_date, end_date, categories=None, locations=None, statuses=None, search=""):
    out = df.copy()
    if out.empty:
        return out
    out["_date"] = pd.to_datetime(out["report_date_db"], errors="coerce")
    out = out[(out["_date"].dt.date >= start_date) & (out["_date"].dt.date <= end_date)]
    if categories:
        out = out[out["category"].isin(categories)]
    if locations:
        out = out[out["location"].isin(locations)]
    if statuses:
        out = out[out["status"].isin(statuses)]
    if search.strip():
        q = search.strip()
        mask = pd.Series(False, index=out.index)
        for c in ["category", "sub_category", "location", "stationing", "activity_detail", "remarks", "pdf_filename"]:
            if c in out.columns:
                mask = mask | out[c].fillna("").astype(str).str.contains(q, case=False, na=False, regex=False)
        out = out[mask]
    return out.drop(columns=["_date"], errors="ignore")


def period_preset(label):
    today = date.today()
    if label == "Current Month":
        return today.replace(day=1), today
    if label == "Previous Month":
        first = today.replace(day=1)
        prev_end = first - timedelta(days=1)
        return prev_end.replace(day=1), prev_end
    if label == "Last 7 Days":
        return today - timedelta(days=6), today
    if label == "Last 30 Days":
        return today - timedelta(days=29), today
    return today, today


def unique_location_count(df):
    if df.empty:
        return 0
    return int(df["location"].fillna("").astype(str).str.strip().replace("", pd.NA).dropna().nunique())


def quantity_summary(df):
    if df.empty:
        return 0.0
    return float(df["quantity"].fillna(0).sum())


def pass_rate(df):
    if df.empty:
        return 0.0
    vals = df["status"].fillna("").astype(str).str.strip().str.lower()
    return float((vals == "pass").mean() * 100)


def export_excel(df, period_label):
    output = io.BytesIO()
    export_cols = ["id", "report_date", "category", "sub_category", "location", "stationing", "activity_detail", "quantity", "unit", "status", "remarks", "pdf_filename"]
    work = df.copy()
    for c in export_cols:
        if c not in work.columns:
            work[c] = ""
    work = work[export_cols]
    work.columns = ["ID", "Date", "Category", "Sub-Category / Layer", "Location", "Stationing", "Technical Activities", "Quantity", "Unit", "Status", "Remarks", "PDF Reference"]
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        work.to_excel(writer, sheet_name="Period Report", index=False)
        wb = writer.book
        ws = writer.sheets["Period Report"]
        header = wb.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#00695C", "border": 1, "align": "center", "valign": "vcenter"})
        body = wb.add_format({"border": 1, "valign": "top", "text_wrap": True})
        num = wb.add_format({"border": 1, "num_format": "#,##0.0"})
        for i, col in enumerate(work.columns):
            ws.write(0, i, col, header)
            # .str.len() is used instead of .map(len): on pandas 3 (Streamlit Cloud) the
            # default text dtype is Arrow-backed, astype(str) keeps missing values as
            # NaN/NA, and .map(len) then raises TypeError on those missing values.
            max_len = int(work[col].astype(str).str.len().fillna(0).max()) if len(work) else 10
            width = min(max(len(col) + 4, max_len + 2), 38)
            ws.set_column(i, i, width)
        for r in range(len(work)):
            for c in range(len(work.columns)):
                val = work.iloc[r, c]
                if isinstance(val, (int, float)) and not pd.isna(val):
                    ws.write_number(r + 1, c, float(val), num if c == 7 else body)
                else:
                    ws.write(r + 1, c, "" if pd.isna(val) else str(val), body)
        ws.freeze_panes(1, 0)
        ws.hide_gridlines(2)
    return output.getvalue()


def generate_html_report(df, start_date, end_date, period_label):
    total_records = len(df)
    total_qty = quantity_summary(df)
    locations = unique_location_count(df)
    rate = pass_rate(df)
    cat = (df.groupby("category", dropna=False).agg(Records=("id", "count"), Quantity=("quantity", "sum")).reset_index().sort_values("Records", ascending=False)) if not df.empty else pd.DataFrame(columns=["category", "Records", "Quantity"])
    loc = (df.groupby("location", dropna=False).agg(Activities=("id", "count"), Quantity=("quantity", "sum")).reset_index().sort_values("Quantity", ascending=False).head(30)) if not df.empty else pd.DataFrame(columns=["location", "Activities", "Quantity"])
    day = (df.assign(_dt=pd.to_datetime(df["report_date_db"], errors="coerce")).groupby("_dt").agg(Records=("id", "count"), Quantity=("quantity", "sum")).reset_index().sort_values("_dt")) if not df.empty else pd.DataFrame(columns=["_dt", "Records", "Quantity"])

    def rows(frame, cols):
        if frame.empty:
            return '<tr><td colspan="%d">No data</td></tr>' % len(cols)
        out = []
        for _, r in frame.iterrows():
            out.append("<tr>" + "".join(f"<td>{safe_html(r[c])}</td>" for c in cols) + "</tr>")
        return "".join(out)

    html = f"""<!doctype html>
<html><head><meta charset='utf-8'><title>EIMS Period Report - {safe_html(period_label)}</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;color:#1f2937;margin:0;background:#f8fafc}}
.container{{max-width:1180px;margin:30px auto;padding:0 24px}}
.header{{background:linear-gradient(135deg,#00695C,#0f766e);color:#fff;padding:26px 30px;border-radius:18px}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:18px 0}}
.card{{background:#fff;border:1px solid #dbe4e8;border-radius:14px;padding:18px;text-align:center}}
.val{{font-size:28px;font-weight:800;margin-top:6px}}
.small{{font-size:13px;color:#64748b}}
table{{width:100%;border-collapse:collapse;background:#fff;margin:10px 0 24px}}th,td{{border:1px solid #dbe4e8;padding:9px;font-size:13px;text-align:left;vertical-align:top}}th{{background:#00695C;color:#fff}}
h2{{color:#00695C;margin-top:30px}}
@media print{{body{{background:#fff}} .container{{margin:0 auto}}}}
</style></head><body><div class='container'>
<div class='header'><div style='font-size:13px;opacity:.85'>EIMS • Engineering Information Management System</div>
<h1>Engineering Works Period Report</h1><div>{safe_html(period_label)} • {start_date.strftime('%d-%m-%Y')} to {end_date.strftime('%d-%m-%Y')}</div></div>
<div class='grid'>
<div class='card'><div class='small'>Inspection Records</div><div class='val'>{total_records:,}</div></div>
<div class='card'><div class='small'>Approved Quantity</div><div class='val'>{total_qty:,.1f}</div></div>
<div class='card'><div class='small'>Locations Covered</div><div class='val'>{locations:,}</div></div>
<div class='card'><div class='small'>Pass Rate</div><div class='val'>{rate:.1f}%</div></div>
</div>
<h2>1. Progress by Category</h2><table><thead><tr><th>Category</th><th>Records</th><th>Quantity</th></tr></thead><tbody>{rows(cat,['category','Records','Quantity'])}</tbody></table>
<h2>2. Progress by Location</h2><table><thead><tr><th>Location</th><th>Activities</th><th>Quantity</th></tr></thead><tbody>{rows(loc,['location','Activities','Quantity'])}</tbody></table>
<h2>3. Daily Progress</h2><table><thead><tr><th>Date</th><th>Records</th><th>Quantity</th></tr></thead><tbody>{rows(day.assign(Date=day['_dt'].dt.strftime('%d-%m-%Y')) if not day.empty else day,['Date','Records','Quantity'])}</tbody></table>
<h2>4. Detailed Registry</h2><table><thead><tr><th>Date</th><th>Category</th><th>Activity</th><th>Location</th><th>Stationing</th><th>Qty</th><th>Unit</th><th>Status</th></tr></thead><tbody>{rows(df[['report_date','category','sub_category','location','stationing','quantity','unit','status']],['report_date','category','sub_category','location','stationing','quantity','unit','status'])}</tbody></table>
<div class='small'>Generated by the local EIMS test build. This file does not modify the connected GitHub repository.</div>
</div></body></html>"""
    return html.encode("utf-8")


def insert_records(records):
    if not records:
        return 0
    inserted = 0
    with db_conn() as conn:
        for rec in records:
            conn.execute("""INSERT INTO master_registry
                (report_date, category, sub_category, location, quantity, unit, status, remarks, pdf_filename, pdf_path, detailed_levels, stationing, activity_detail)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                normalize_date(rec.get("report_date")), rec.get("category", "Unknown"), rec.get("sub_category", "Imported Activity"),
                rec.get("location", "Unknown"), float(rec.get("quantity", 0) or 0), rec.get("unit", "Unit"), rec.get("status", "Pass"),
                rec.get("remarks", ""), rec.get("pdf_filename"), rec.get("pdf_path"), json.dumps(rec.get("detailed_levels", [])) if rec.get("detailed_levels") else None,
                rec.get("stationing"), rec.get("activity_detail")
            ))
            inserted += 1
    return inserted


def parse_csv(upload):
    data = pd.read_csv(upload)
    mapping = {
        "Report Date":"report_date", "Main Category":"category", "Sub-category":"sub_category", "Location":"location",
        "Stationing":"stationing", "Quantity Approved":"quantity", "Unit":"unit", "PDF Attachment Name":"pdf_filename", "Remarks":"remarks"
    }
    data = data.rename(columns=mapping)
    required = ["report_date","category","sub_category","location","quantity","unit"]
    missing = [c for c in required if c not in data.columns]
    if missing:
        raise ValueError("Missing columns: " + ", ".join(missing))
    return data.fillna("").to_dict("records")


def parse_html_file(upload):
    content = upload.getvalue().decode("utf-8", errors="ignore")
    soup = BeautifulSoup(content, "html.parser")
    text = soup.get_text(" ", strip=True)
    date_match = re.search(r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})", text, re.I)
    report_date = None
    if date_match:
        report_date = datetime.strptime(f"{date_match.group(1)} {date_match.group(2)[:3]} {date_match.group(3)}", "%d %b %Y").strftime("%Y-%m-%d")
    tables = pd.read_html(io.StringIO(content))
    if not tables:
        return []
    records = []
    for tbl in tables:
        cols = [str(c).strip().lower() for c in tbl.columns]
        joined = " ".join(cols)
        if "quantity" in joined or "length" in joined or "chainage" in joined:
            records.append({
                "report_date": report_date or date.today().isoformat(),
                "category": "Imported Engineering Works",
                "sub_category": "Imported HTML Activity",
                "location": "See HTML report",
                "quantity": float(pd.to_numeric(tbl.select_dtypes(include='number').sum().sum(), errors='coerce') or 0),
                "unit": "Unit",
                "status": "Pass",
                "remarks": f"Imported from HTML attachment: {getattr(upload,'name','report.html')}"
            })
            break
    return records


def render_kpi_card(title, value, note=""):
    st.markdown(f"<div class='metric-card'><div class='metric-title'>{safe_html(title)}</div><div class='metric-val'>{safe_html(value)}</div><div class='metric-note'>{safe_html(note)}</div></div>", unsafe_allow_html=True)


ensure_schema()

df = load_data()

st.sidebar.markdown("""<div style='text-align:center;padding:12px 0 18px'><div style='font-size:24px;font-weight:800;color:#00695C'>🛡️ EIMS System</div><div class='small-muted'>Engineering Information Management</div></div>""", unsafe_allow_html=True)
menu = st.sidebar.radio("Main Navigation", ["📊 Dashboard", "📋 Master Registry", "📈 Progress & Reports", "📥 Import Engineering Reports"], index=0)

with st.sidebar.expander("⚙️ Paths & References Settings", expanded=False):
    st.caption("EIMS reads the scanned PDF reports and the processed HTML audits from the folders below. "
               "Changes are saved permanently in the database and applied immediately.")

    _cur_pdf   = get_setting("pdf_dir", "") or DEFAULT_PDF_DIR
    _cur_html  = get_setting("html_dir", "") or DEFAULT_HTML_DIR
    _cur_extra = get_setting("extra_pdf_dirs", "") or ""

    _new_pdf   = st.text_input("\U0001F4C1 PDF reports folder (scanned PDFs):", value=_cur_pdf, key="cfg_pdf_dir")
    _new_html  = st.text_input("\U0001F310 HTML audits folder (Processed_Audits):", value=_cur_html, key="cfg_html_dir")
    _new_extra = st.text_area("Additional search folders (one per line, optional):", value=_cur_extra,
                              key="cfg_extra_dirs", height=68)

    for _label, _d in (("PDFs", _new_pdf), ("HTML", _new_html)):
        if _d and os.path.isdir(_d):
            try:
                _n = len([f for f in os.listdir(_d) if os.path.isfile(os.path.join(_d, f))])
            except Exception:
                _n = 0
            st.markdown(f"\u2705 **{_label}**: `{_d}` - {_n} file(s)")
        else:
            st.markdown(f"\u274C **{_label}**: `{_d}` - folder not found")

    _c1, _c2 = st.columns(2)
    with _c1:
        if st.button("\U0001F4BE Save paths", use_container_width=True, key="cfg_save_paths"):
            save_setting("pdf_dir", (_new_pdf or "").strip())
            save_setting("html_dir", (_new_html or "").strip())
            save_setting("extra_pdf_dirs", _new_extra or "")
            save_setting("custom_pdf_dir", (_new_pdf or "").strip())
            st.success("Paths saved successfully.")
            st.rerun()
    with _c2:
        if st.button("\U0001F527 Fix stored PDF links", use_container_width=True, key="cfg_fix_paths",
                     help="Rewrite the PDF paths saved inside the database so they point to the folders above."):
            _fixed, _missing = repair_stored_pdf_paths()
            st.success(f"Updated {_fixed} link(s)." + (f" {_missing} file(s) could not be found." if _missing else ""))
            st.rerun()

if menu == "📊 Dashboard":
    st.markdown("<div class='eims-hero'><h1>📊 EIMS Master Dashboard</h1><div class='section-note'>All engineering results, KPIs, search, filters, registry and record inspection are available on this main page.</div></div>", unsafe_allow_html=True)
    if df.empty:
        st.info("The database is empty.")
    else:
        # 1. High-level KPIs — compact, consistent and driven by current results.
        st.markdown("### 📈 Engineering Summary")
        c1, c2, c3, c4 = st.columns(4)
        with c1: render_kpi_card("Total Inspection Records", f"{len(df):,}", "all records")
        with c2: render_kpi_card("Approved Quantity", f"{quantity_summary(df):,.1f}", "all recorded units")
        with c3: render_kpi_card("Locations Covered", f"{unique_location_count(df):,}", "unique locations")
        with c4: render_kpi_card("Pass Rate", f"{pass_rate(df):.1f}%", "all records")

        st.markdown("---")
        # 2. Original-style universal search and filters. Search every important field.
        st.markdown("### 🔎 Advanced Search & Filter Options")
        f1, f2, f3, f4, f5 = st.columns([2.25, 1.0, 1.2, 1.1, 1.0])
        with f1:
            search_query = st.text_input(
                "📝 Universal Smart Search — search across all record fields",
                placeholder="ID, date, category, activity, location, stationing, quantity, unit, status, remarks, PDF…",
                key="home_global_search"
            )
        with f2:
            unique_dates = sorted(distinct_nonempty(df, "report_date"), reverse=True)
            sel_date = st.selectbox("📅 Filter by Date", ["All"] + unique_dates, key="home_date")
        with f3:
            sel_cat = st.selectbox("📂 Main Category", ["All"] + distinct_nonempty(df, "category"), key="home_cat")
        with f4:
            sel_sub = st.selectbox("🎯 Activity / Layer", ["All"] + distinct_nonempty(df, "sub_category"), key="home_sub")
        with f5:
            sel_status = st.selectbox("🛡️ Status", ["All"] + distinct_nonempty(df, "status"), key="home_status")

        filtered = df.copy()
        if search_query.strip():
            q = search_query.strip()
            # Deliberately search all user-facing database columns, including numeric/date values.
            searchable_cols = [c for c in df.columns if c != "report_date_db"]
            mask = pd.Series(False, index=filtered.index)
            for col in searchable_cols:
                vals = filtered[col].fillna("").astype(str)
                mask = mask | vals.str.contains(q, case=False, na=False, regex=False)
            filtered = filtered[mask]
        if sel_date != "All":
            filtered = filtered[filtered["report_date"] == sel_date]
        if sel_cat != "All":
            filtered = filtered[filtered["category"] == sel_cat]
        if sel_sub != "All":
            filtered = filtered[filtered["sub_category"] == sel_sub]
        if sel_status != "All":
            filtered = filtered[filtered["status"] == sel_status]

        # Default = newest imported first (highest Record ID) so a freshly imported
        # batch is always visible at the top, even if its report date is older.
        _sort_choices = [
            "🆕 Newest imported first (Record ID ↓)",
            "📅 Report date ↓ (newest work first)",
            "📅 Report date ↑ (oldest work first)",
            "🔢 Record ID ↑ (oldest imported first)",
        ]
        _sel_sort = st.selectbox("🔢 Sort registry by:", _sort_choices, index=0)
        if _sel_sort == _sort_choices[0]:
            filtered = filtered.sort_values("id", ascending=False)
        elif _sel_sort == _sort_choices[1]:
            _dt = pd.to_datetime(filtered["report_date"], format="%d-%m-%Y", errors="coerce")
            filtered = filtered.assign(_dt=_dt).sort_values(["_dt", "id"], ascending=[False, False]).drop(columns=["_dt"])
        elif _sel_sort == _sort_choices[2]:
            _dt = pd.to_datetime(filtered["report_date"], format="%d-%m-%Y", errors="coerce")
            filtered = filtered.assign(_dt=_dt).sort_values(["_dt", "id"], ascending=[True, True]).drop(columns=["_dt"])
        else:
            filtered = filtered.sort_values("id", ascending=True)

        st.markdown(f"📊 Found **{len(filtered):,}** inspection records matching the current filters.")
        st.caption(f"Latest record ID in database: **{int(df['id'].max()) if not df.empty else 0}**")

        # 3. Main registry remains on the homepage, as in the original workflow.
        st.markdown("### 📋 Master Engineering Registry")
        cols = [
            "id", "report_date", "category", "sub_category", "location", "stationing",
            "activity_detail", "quantity", "unit", "status", "remarks", "pdf_filename"
        ]
        existing_cols = [c for c in cols if c in filtered.columns]
        display = filtered[existing_cols].copy()
        display.columns = [
            "ID", "📅 Report Date", "📂 Main Category", "🎯 Sub-category / Layer", "📍 Location",
            "🛣️ Stationing", "🔬 Technical Activity Details", "📏 Quantity", "⚙️ Unit",
            "🛡️ Audit Decision", "💬 Remarks & Tolerance", "📄 PDF Reference"
        ][:len(existing_cols)]
        st.dataframe(display, use_container_width=True, hide_index=True)

        # 4. Export the currently visible result set.
        st.download_button(
            "📊 Export Current Results to Excel",
            export_excel(filtered, "Current Dashboard Results"),
            file_name="EIMS_Current_Dashboard_Results.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        # 5. Selected row / engineering inspector stays directly below the registry.
        st.markdown("### 🔍 Level Audit & Engineering Detail Inspector")
        selected_id = st.selectbox(
            "Select Record ID to view level details and engineering information:",
            filtered["id"].tolist() if not filtered.empty else [],
            key="home_selected_id"
        )
        if selected_id:
            row = df[df["id"] == selected_id].iloc[0]
            a, b, c = st.columns(3)
            a.write(f"**Execution / Report Date:** {row['report_date']}")
            b.write(f"**Project Category:** {row['category']}")
            c.write(f"**Location:** {row['location']}")
            a.write(f"**Sub-category / Layer:** {row['sub_category']}")
            b.write(f"**Stationing:** {row['stationing'] or '—'}")
            c.write(f"**Approved Quantity:** {row['quantity']:,.1f} {row['unit']}")
            st.write(f"**Technical Activity Details:** {row['activity_detail'] or '—'}")
            st.write(f"**Audit Decision:** {row['status']}")
            st.write(f"**Consultant Remarks & Tolerance:** {row['remarks'] or '—'}")

            # Preserve convenient local PDF/HTML actions when references exist.
            # The stored path is used when it still exists; otherwise the file is looked
            # up by name inside every configured folder (handles the move to drive D:).
            target_pdf_path = resolve_pdf_path(row.get("pdf_path"), row.get("pdf_filename"))
            target_pdf_filename = row.get("pdf_filename")
            if target_pdf_path:
                target_pdf_filename = os.path.basename(target_pdf_path) or target_pdf_filename
                if not row.get("pdf_path") or str(row.get("pdf_path")) != str(target_pdf_path):
                    try:
                        with db_conn() as _conn_fix:
                            _conn_fix.execute("UPDATE master_registry SET pdf_path = ? WHERE id = ?",
                                              (target_pdf_path, int(selected_id)))
                    except Exception:
                        pass
            if target_pdf_path and os.path.exists(target_pdf_path):
                b1, b2, b3 = st.columns(3)
                with b1:
                    if st.button("📂 Open PDF", use_container_width=True, key=f"open_pdf_{selected_id}"):
                        try:
                            os.startfile(target_pdf_path)
                        except Exception as exc:
                            st.error(f"Could not open the PDF locally: {exc}")
                with b2:
                    html_filename = (os.path.splitext(target_pdf_filename)[0] + ".html") if target_pdf_filename else None
                    html_path = os.path.join(get_html_dir(), html_filename) if html_filename else None
                    if html_path and not os.path.exists(html_path):
                        for _sd in get_pdf_search_dirs():
                            _found_html = find_file_case_insensitive(_sd, html_filename)
                            if _found_html:
                                html_path = _found_html
                                break
                    if st.button("🌐 Open HTML", use_container_width=True, key=f"open_html_{selected_id}"):
                        if html_path and os.path.exists(html_path):
                            try:
                                os.startfile(html_path)
                            except Exception as exc:
                                st.error(f"Could not open the HTML locally: {exc}")
                        else:
                            st.warning("Matching HTML report was not found locally.")
                with b3:
                    with open(target_pdf_path, "rb") as handle:
                        st.download_button(
                            "📥 Download PDF",
                            data=handle,
                            file_name=target_pdf_filename or "EIMS_Report.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                            key=f"download_pdf_{selected_id}",
                        )

elif menu == "📋 Master Registry":
    st.markdown("<div class='eims-hero'><h1>📋 Master Engineering Registry</h1><div class='section-note'>Complete searchable registry of all engineering inspection records.</div></div>", unsafe_allow_html=True)
    if df.empty:
        st.info("The database is empty.")
    else:
        st.markdown("### 🔎 Search & Filter Registry")
        f1, f2, f3, f4, f5 = st.columns([2.25, 1.0, 1.2, 1.1, 1.0])
        with f1:
            registry_search = st.text_input(
                "📝 Universal Smart Search — searches all fields",
                placeholder="ID, date, category, sub-category, location, stationing, quantity, status, remarks, PDF…",
                key="registry_global_search"
            )
        with f2:
            sel_date_r = st.selectbox("📅 Date", ["All"] + sorted(distinct_nonempty(df, "report_date"), reverse=True), key="registry_date")
        with f3:
            sel_cat_r = st.selectbox("📂 Main Category", ["All"] + distinct_nonempty(df, "category"), key="registry_cat")
        with f4:
            sel_sub_r = st.selectbox("🎯 Activity / Layer", ["All"] + distinct_nonempty(df, "sub_category"), key="registry_sub")
        with f5:
            sel_status_r = st.selectbox("🛡️ Status", ["All"] + distinct_nonempty(df, "status"), key="registry_status")

        registry = df.copy()
        if registry_search.strip():
            q = registry_search.strip()
            mask = pd.Series(False, index=registry.index)
            for col in registry.columns:
                if col == "report_date_db":
                    continue
                mask |= registry[col].fillna("").astype(str).str.contains(q, case=False, na=False, regex=False)
            registry = registry[mask]
        if sel_date_r != "All":
            registry = registry[registry["report_date"] == sel_date_r]
        if sel_cat_r != "All":
            registry = registry[registry["category"] == sel_cat_r]
        if sel_sub_r != "All":
            registry = registry[registry["sub_category"] == sel_sub_r]
        if sel_status_r != "All":
            registry = registry[registry["status"] == sel_status_r]

        st.markdown(f"📊 Showing **{len(registry):,}** records.")
        registry_cols = [
            "id", "report_date", "category", "sub_category", "location", "stationing",
            "activity_detail", "quantity", "unit", "status", "remarks", "pdf_filename"
        ]
        registry_cols = [c for c in registry_cols if c in registry.columns]
        reg_display = registry[registry_cols].copy()
        header_map = {
            "id":"ID", "report_date":"📅 Report Date", "category":"📂 Main Category",
            "sub_category":"🎯 Sub-category / Layer", "location":"📍 Location",
            "stationing":"🛣️ Stationing", "activity_detail":"🔬 Technical Activity Details",
            "quantity":"📏 Quantity", "unit":"⚙️ Unit", "status":"🛡️ Audit Decision",
            "remarks":"💬 Remarks & Tolerance", "pdf_filename":"📄 PDF Reference"
        }
        reg_display = reg_display.rename(columns={c: header_map.get(c,c) for c in reg_display.columns})
        st.dataframe(reg_display, use_container_width=True, hide_index=True)

        st.markdown("### 🔍 Engineering Record Inspector")
        selected_rid = st.selectbox("Select Record ID:", registry["id"].tolist() if not registry.empty else [], key="registry_selected_id")
        if selected_rid:
            row = df[df["id"] == selected_rid].iloc[0]
            a,b,c = st.columns(3)
            a.write(f"**Report Date:** {row['report_date']}")
            b.write(f"**Category:** {row['category']}")
            c.write(f"**Location:** {row['location']}")
            a.write(f"**Sub-category / Layer:** {row['sub_category']}")
            b.write(f"**Stationing:** {row['stationing'] or '—'}")
            c.write(f"**Quantity:** {row['quantity']:,.1f} {row['unit']}")
            st.write(f"**Technical Activity Details:** {row['activity_detail'] or '—'}")
            st.write(f"**Status:** {row['status']}")
            st.write(f"**Remarks:** {row['remarks'] or '—'}")
            st.download_button(
                "📊 Export Filtered Registry to Excel",
                export_excel(registry, "Master Registry"),
                file_name="EIMS_Master_Registry_Filtered.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

elif menu == "📈 Progress & Reports":
    st.markdown("<div class='eims-hero'><h1>📈 Progress & Reports</h1><div class='section-note'>Generate a period-based engineering progress report for a month, a week, or any custom date range.</div></div>", unsafe_allow_html=True)
    if df.empty:
        st.info("No records available to report.")
    else:
        preset = st.radio("Report Period", ["Current Month","Previous Month","Last 7 Days","Last 30 Days","Custom Range"], horizontal=True, index=0)
        if preset == "Custom Range":
            c1,c2 = st.columns(2)
            default_end = pd.to_datetime(df["report_date_db"]).max().date()
            default_start = default_end.replace(day=1)
            with c1: start = st.date_input("From", value=default_start, min_value=pd.to_datetime(df["report_date_db"]).min().date(), max_value=default_end, key="rep_custom_start")
            with c2: end = st.date_input("To", value=default_end, min_value=start, max_value=default_end, key="rep_custom_end")
            period_label = "Custom Range"
        else:
            start, end = period_preset(preset)
            min_db = pd.to_datetime(df["report_date_db"]).min().date()
            max_db = pd.to_datetime(df["report_date_db"]).max().date()
            start = max(start, min_db); end = min(end, max_db)
            period_label = preset
        if start > end:
            st.error("The start date cannot be after the end date.")
            st.stop()

        f1,f2,f3 = st.columns([1.3,1.3,2.2])
        with f1: category_filter = st.multiselect("Category", distinct_nonempty(df,"category"), key="rep_cat")
        with f2: location_filter = st.multiselect("Location", distinct_nonempty(df,"location"), key="rep_loc")
        with f3: search_filter = st.text_input("Additional Search", placeholder="Optional keyword", key="rep_search")
        report_df = apply_filters(df, start, end, category_filter, location_filter, None, search_filter)

        st.markdown(f"**{period_label}** — {start.strftime('%d-%m-%Y')} → {end.strftime('%d-%m-%Y')} — **{len(report_df):,} records**")
        k1,k2,k3,k4 = st.columns(4)
        with k1: render_kpi_card("Inspection Records", f"{len(report_df):,}")
        with k2: render_kpi_card("Approved Quantity", f"{quantity_summary(report_df):,.1f}", "all recorded units")
        with k3: render_kpi_card("Locations Covered", f"{unique_location_count(report_df):,}")
        with k4: render_kpi_card("Pass Rate", f"{pass_rate(report_df):.1f}%")

        st.markdown("### Category Progress")
        if report_df.empty:
            st.info("No records match the selected period and filters.")
        else:
            cat = report_df.groupby("category", as_index=False).agg(Records=("id","count"), Quantity=("quantity","sum")).sort_values("Quantity", ascending=False)
            st.dataframe(cat, use_container_width=True, hide_index=True)
            st.bar_chart(cat.set_index("category")["Quantity"])

            st.markdown("### Location Progress")
            loc = report_df.groupby("location", as_index=False).agg(Activities=("id","count"), Quantity=("quantity","sum")).sort_values("Quantity", ascending=False)
            st.dataframe(loc.head(30), use_container_width=True, hide_index=True)

            st.markdown("### Daily Progress")
            daily = report_df.copy()
            daily["Date"] = pd.to_datetime(daily["report_date_db"])
            daily = daily.groupby("Date", as_index=False).agg(Records=("id","count"), Quantity=("quantity","sum")).sort_values("Date")
            chart = daily.set_index("Date")["Quantity"]
            st.line_chart(chart)
            st.dataframe(daily.assign(Date=daily["Date"].dt.strftime("%d-%m-%Y")), use_container_width=True, hide_index=True)

        st.markdown("### Export")
        ec1,ec2 = st.columns(2)
        with ec1:
            st.download_button("📊 Export Excel", export_excel(report_df, period_label), file_name=f"EIMS_{start.isoformat()}_{end.isoformat()}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        with ec2:
            st.download_button("🌐 Generate HTML Report", generate_html_report(report_df, start, end, period_label), file_name=f"EIMS_{start.isoformat()}_{end.isoformat()}.html", mime="text/html", use_container_width=True)
        st.caption("The HTML report is print-friendly; from your browser you can use Print → Save as PDF for a PDF copy.")

elif menu == "📥 Import Engineering Reports":
    st.markdown("<div class='eims-hero'><h1>📥 Import Engineering Reports</h1><div class='section-note'>Local test importer for CSV/Excel-style progress data and basic HTML report extraction.</div></div>", unsafe_allow_html=True)
    password = st.sidebar.text_input("Admin Password", type="password")
    if password != "1212":
        st.warning("Enter the admin password to access the importer.")
        st.stop()
    mode = st.radio("Import Method", ["CSV", "HTML"], horizontal=True)
    uploaded = st.file_uploader("Upload source file", type=["csv","html","htm"])
    if uploaded:
        try:
            parsed = parse_csv(uploaded) if mode == "CSV" else parse_html_file(uploaded)
            st.write(f"Parsed **{len(parsed)}** record(s).")
            if parsed:
                st.dataframe(pd.DataFrame(parsed), use_container_width=True, hide_index=True)
                if st.button("Insert Parsed Records", type="primary"):
                    n = insert_records(parsed)
                    st.success(f"Inserted {n} record(s).")
                    st.cache_data.clear()
                    st.rerun()
            else:
                st.warning("No compatible records were found.")
        except Exception as exc:
            st.error(f"Import failed: {exc}")

st.sidebar.markdown("---")
st.sidebar.caption("LOCAL TEST BUILD • main branch was not modified")
st.sidebar.caption(f"Database: {DB_NAME} • Records: {len(df):,}")
