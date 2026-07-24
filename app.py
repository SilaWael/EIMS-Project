# -*- coding: utf-8 -*-
"""
EIMS — Engineering Information Management System (Cloud Edition)
================================================================
Cloud-native version of the original EIMS Streamlit app.
- Database: Supabase Postgres (replaces SQLite eims.db)
- Storage: Supabase Storage (replaces local Finished PDFs/, Processed_Audits/, CSV Data Base Files/)
- Deployment: Streamlit Cloud (auto-redeploy from GitHub)

Supervisor: Eng. Wael Radwan — ADHA Project (108 Villas)
"""
import streamlit as st
import pandas as pd
import json
import os
import re
import io
from datetime import datetime

import db
from db import (
    load_data, save_record, delete_record, save_setting, get_setting,
    match_category_index, normalize_date_to_db, format_date_to_display,
    heal_database, get_supabase_client, get_pdf_public_url, get_html_public_url,
    upload_to_storage, log_action, CONFIG,
)

# ============================================================
# Page config
# ============================================================
st.set_page_config(
    page_title="EIMS — Engineering Information Management System",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Premium CSS
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&family=Outfit:wght@300;400;600;700&display=swap');
    html, body, [class*="css"], .stMarkdown {
        font-family: 'Cairo', 'Outfit', sans-serif;
    }
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
    .metric-title { font-size: 0.95rem; opacity: 0.85; margin-bottom: 0.5rem; font-weight: 600; }
    .metric-val { font-size: 2rem; font-weight: 800; color: #0284c7; }
    .metric-unit { font-size: 1rem; color: #00695C; font-weight: 700; margin-left: 0.25rem; }
    .badge { padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.85rem; font-weight: 700; display: inline-block; }
    .badge-pass { background-color: rgba(16, 185, 129, 0.2); color: #10b981; }
    .badge-fail { background-color: rgba(239, 68, 68, 0.2); color: #ef4848; }
    </style>
""", unsafe_allow_html=True)

# ============================================================
# Sidebar
# ============================================================
st.sidebar.markdown("""
    <div style="text-align: center; padding: 1rem 0;">
        <h2 style="color: #0284c7; font-weight: 800; margin-bottom: 0;">🛡️ EIMS Cloud</h2>
        <p style="color: #94a3b8; font-size: 0.9rem;">Engineering Information Management</p>
        <hr style="border-color: rgba(226, 232, 240, 0.1); margin-top: 0.5rem;"/>
    </div>
""", unsafe_allow_html=True)

menu = st.sidebar.radio(
    "💬 Main Navigation",
    ["📊 Master Dashboard", "📥 Import Engineering Reports", "☁️ Cloud Status"],
    index=0
)

st.sidebar.markdown("<br>", unsafe_allow_html=True)
st.sidebar.markdown("""
    <div style="font-size: 0.8rem; color: #64748b; text-align: center; border-top: 1px solid rgba(226, 232, 240, 0.05); padding-top: 10px;">
        👨‍💻 Supervision: Eng. <strong>Wael Radwan</strong><br>
        108 Villas Project — ADHA<br>
        <em style="color: #0284c7;">Cloud Edition (Supabase)</em>
    </div>
""", unsafe_allow_html=True)


# ============================================================
# TAB 1: Master Dashboard
# ============================================================
if menu == "📊 Master Dashboard":
    st.markdown("<h1 style='color: #0284c7;'>📊 Master Registry Dashboard</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color: #94a3b8; margin-top: -10px;'>Comprehensive registry of construction audits, approved quantities, level details, and PDF references.</p>", unsafe_allow_html=True)

    try:
        records = load_data()
    except Exception as e:
        st.error(f"❌ Failed to load data from Supabase: {e}")
        st.info("Check that all secrets are set in Streamlit Cloud → App Settings → Secrets")
        st.stop()

    if not records:
        st.info("👋 The database is currently empty. Use the 'Import Engineering Reports' tab to upload CSVs.")
        st.stop()

    df = pd.DataFrame(records)

    # --- Metric cards ---
    st.markdown("### 📈 Approved Cumulative Engineering Quantities")

    all_road_layers = df[df['category'].str.contains("Road", case=False, na=False)]['sub_category'].unique()
    col_sel, _ = st.columns([1, 3])
    with col_sel:
        selected_road_layer = st.selectbox(
            "🛣️ Cumulative Roads Layer (Road Works only):",
            all_road_layers if len(all_road_layers) > 0 else ["Subgrade 2nd Layer"]
        )

    road_df = df[(df['category'].str.contains("Road", case=False, na=False)) & (df['sub_category'] == selected_road_layer)]
    total_roads = road_df['quantity'].sum()
    wet_df = df[df['category'].str.contains("Water|Irrigation|Wet", case=False, na=False)]
    total_wet = wet_df['quantity'].sum()
    dry_df = df[df['category'].str.contains("Dry|Lighting|Telecom|MCC", case=False, na=False)]
    total_dry = dry_df['quantity'].sum()
    struct_df = df[df['category'].str.contains("Struct|Crossing|Manhole", case=False, na=False)]
    total_struct = len(struct_df)

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(f"""<div class="metric-card"><div class="metric-title">Total Roads Approved ({selected_road_layer})</div><div class="metric-val">{total_roads:,.2f}<span class="metric-unit"> m</span></div></div>""", unsafe_allow_html=True)
    with m2:
        st.markdown(f"""<div class="metric-card"><div class="metric-title">Wet Utilities (Water/Irrigation)</div><div class="metric-val">{total_wet:,.2f}<span class="metric-unit"> m</span></div></div>""", unsafe_allow_html=True)
    with m3:
        st.markdown(f"""<div class="metric-card"><div class="metric-title">Dry Utilities & Security</div><div class="metric-val">{total_dry:,.2f}<span class="metric-unit"> m</span></div></div>""", unsafe_allow_html=True)
    with m4:
        st.markdown(f"""<div class="metric-card"><div class="metric-title">Civil Structures & Crossings</div><div class="metric-val">{total_struct}<span class="metric-unit"> Unit</span></div></div>""", unsafe_allow_html=True)

    st.markdown("<hr style='border-color: rgba(226, 232, 240, 0.1);'/>", unsafe_allow_html=True)

    # --- Filters ---
    st.markdown("### 🔍 Advanced Search & Filter Options")
    f1, f2, f3, f4, f5 = st.columns(5)
    with f1:
        search_query = st.text_input("📝 Universal Smart Search:", placeholder="Subgrade, Road-05, Feeder Pillar...")
    with f2:
        unique_dates = sorted([d for d in df['report_date'].dropna().unique()], reverse=True)
        sel_date = st.selectbox("📅 Filter by Date:", ["All"] + list(unique_dates))
    with f3:
        sel_cat = st.selectbox("📂 Filter by Main Category:", ["All"] + list(df['category'].unique()))
    with f4:
        sel_sub = st.selectbox("🎯 Filter by Activity / Layer:", ["All"] + list(df['sub_category'].unique()))
    with f5:
        sel_status = st.selectbox("🛡️ Filter by Status:", ["All"] + list(df['status'].unique()))

    df_filtered = df.copy()
    if search_query:
        mask = pd.Series(False, index=df_filtered.index)
        for col in ['location', 'remarks', 'sub_category', 'category', 'stationing', 'activity_detail', 'pdf_filename']:
            if col in df_filtered.columns:
                mask = mask | df_filtered[col].astype(str).str.contains(search_query, case=False, na=False)
        df_filtered = df_filtered[mask]
    if sel_date != "All":
        df_filtered = df_filtered[df_filtered['report_date'] == sel_date]
    if sel_cat != "All":
        df_filtered = df_filtered[df_filtered['category'] == sel_cat]
    if sel_sub != "All":
        df_filtered = df_filtered[df_filtered['sub_category'] == sel_sub]
    if sel_status != "All":
        df_filtered = df_filtered[df_filtered['status'] == sel_status]

    st.markdown(f"📊 Found **{len(df_filtered)}** inspection records matching the current filters.")

    # Column visibility
    col_options = {
        "id": "ID", "report_date": "📅 Report Date", "category": "📂 Main Category",
        "sub_category": "🎯 Sub-category / Layer", "location": "📍 Location Name",
        "stationing": "🛣️ Stationing (Chainage)", "activity_detail": "🔬 Technical Activity Details",
        "quantity": "📏 Quantity Approved", "unit": "⚙️ Unit", "status": "🛡️ Audit Decision",
        "remarks": "💬 Consultant Remarks", "pdf_filename": "📄 PDF Reference"
    }
    if 'visible_columns' not in st.session_state:
        saved = get_setting('visible_columns')
        if saved:
            try:
                st.session_state['visible_columns'] = json.loads(saved)
            except Exception:
                st.session_state['visible_columns'] = list(col_options.keys())
        else:
            st.session_state['visible_columns'] = list(col_options.keys())

    with st.expander("👁️ Customize Table Columns"):
        selected_cols = st.multiselect(
            "Choose columns:",
            options=list(col_options.keys()),
            default=st.session_state['visible_columns'],
            format_func=lambda x: col_options[x]
        )
        if selected_cols != st.session_state['visible_columns']:
            st.session_state['visible_columns'] = selected_cols
            save_setting('visible_columns', json.dumps(selected_cols))

    display_cols = [c for c in st.session_state['visible_columns'] if c in df_filtered.columns]
    if not display_cols:
        display_cols = ["id", "report_date", "category", "sub_category", "location"]
    df_display = df_filtered[display_cols].copy()

    all_col_config = {
        "id": "ID",
        "report_date": st.column_config.TextColumn("📅 Report Date"),
        "category": st.column_config.TextColumn("📂 Main Category"),
        "sub_category": st.column_config.TextColumn("🎯 Sub-category / Layer"),
        "location": st.column_config.TextColumn("📍 Location Name"),
        "stationing": st.column_config.TextColumn("🛣️ Stationing (Chainage)"),
        "activity_detail": st.column_config.TextColumn("🔬 Technical Activity Details"),
        "quantity": st.column_config.NumberColumn("📏 Quantity Approved", format="%.2f"),
        "unit": st.column_config.TextColumn("⚙️ Unit"),
        "status": st.column_config.TextColumn("🛡️ Audit Decision"),
        "remarks": st.column_config.TextColumn("💬 Consultant Remarks"),
        "pdf_filename": st.column_config.TextColumn("📄 PDF Reference")
    }
    active_col_config = {k: v for k, v in all_col_config.items() if k in display_cols}

    st.dataframe(df_display, use_container_width=True, column_config=active_col_config, hide_index=True)

    st.markdown("<hr style='border-color: rgba(226, 232, 240, 0.1);'/>", unsafe_allow_html=True)

    # --- Record detail inspector ---
    st.markdown("### 🔎 Level Audit & Engineering Detail Inspector")
    if len(df_filtered) > 0:
        selected_id = st.selectbox("👉 Select Record ID to view details:", df_filtered['id'].unique())
        if selected_id:
            row = df[df['id'] == selected_id].iloc[0]
            st.markdown(f"""
                <div style="background-color: rgba(128, 128, 128, 0.05); padding: 1.5rem; border-radius: 8px; border-right: 4px solid #0284c7; margin-bottom: 1rem;">
                    <h4 style="margin-top:0; color:#0284c7;">📍 Engineering Progress Detail Card</h4>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem;">
                        <div><p><strong>Report Date:</strong></p><p style="font-size: 1.1rem;">{row['report_date']}</p></div>
                        <div><p><strong>Category:</strong></p><p style="font-size: 1.1rem;">{row['category']}</p></div>
                        <div><p><strong>Sub-category:</strong></p><p style="font-size: 1.1rem;">{row['sub_category']}</p></div>
                        <div><p><strong>Location:</strong></p><p style="font-size: 1.1rem;">{row['location']}</p></div>
                        <div><p><strong>Quantity:</strong></p><p style="color: #10b981; font-size: 1.2rem; font-weight: bold;">{row['quantity']:.2f} {row['unit']}</p></div>
                        <div><p><strong>Stationing:</strong></p><p style="font-size: 1.1rem;">{row.get('stationing', '') or ''}</p></div>
                    </div>
                    <div style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid rgba(128,128,128,0.2);">
                        <p><strong>Remarks:</strong></p>
                        <p style="opacity: 0.85;">{row.get('remarks') or 'No remarks available.'}</p>
                    </div>
                </div>
            """, unsafe_allow_html=True)

            # Cloud-aware PDF / HTML opening
            pdf_filename = row.get('pdf_filename')
            pdf_path = row.get('pdf_path')

            c1, c2, c3 = st.columns([1, 1, 1])
            with c1:
                if pdf_path and pdf_path.startswith('http'):
                    st.link_button("📂 Open PDF (Cloud)", pdf_path, use_container_width=True)
                elif pdf_path and os.path.exists(str(pdf_path)):
                    if st.button("📂 Open PDF (Local)", use_container_width=True):
                        try:
                            import subprocess
                            subprocess.Popen(['xdg-open', pdf_path])
                        except Exception:
                            st.error("Cannot open local file.")
                else:
                    st.warning("No PDF available.")
            with c2:
                if pdf_filename:
                    html_name = os.path.splitext(pdf_filename)[0] + ".html"
                    html_url = get_html_public_url(html_name)
                    st.link_button("🌐 Open HTML (Cloud)", html_url, use_container_width=True)
            with c3:
                if pdf_path and pdf_path.startswith('http'):
                    try:
                        import requests
                        r = requests.head(pdf_path, timeout=5)
                        if r.status_code == 200:
                            st.success("✓ PDF available in cloud storage")
                        else:
                            st.warning("⚠ PDF not yet uploaded to cloud")
                    except Exception:
                        st.info("? PDF availability unknown")
                else:
                    st.info("Local file")

    # Excel export
    st.markdown("<hr style='border-color: rgba(226, 232, 240, 0.1);'/>", unsafe_allow_html=True)
    st.markdown("### 📥 Export Filtered Data")
    if st.button("📊 Generate Excel Export", use_container_width=False):
        output = io.BytesIO()
        cols_to_export = ["id", "report_date", "category", "sub_category", "location", "stationing",
                          "activity_detail", "quantity", "unit", "status", "remarks", "pdf_filename"]
        df_exp = df_filtered[[c for c in cols_to_export if c in df_filtered.columns]].copy()
        df_exp.columns = ["ID", "Date", "Category", "Sub-Category", "Location Scope", "Detailed Stationing",
                          "Technical Activities Detail", "Quantity", "Unit", "Approval Status",
                          "Remarks / Tolerance", "PDF Reference Filename"]
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_exp.to_excel(writer, sheet_name='EIMS Master Registry', index=False)
            wb = writer.book
            ws = writer.sheets['EIMS Master Registry']
            hf = wb.add_format({'bold': True, 'text_wrap': True, 'valign': 'vcenter',
                                'fg_color': '#00695C', 'font_color': '#FFFFFF',
                                'border': 1, 'font_name': 'Segoe UI', 'font_size': 11, 'align': 'center'})
            cf = wb.add_format({'valign': 'vcenter', 'font_name': 'Segoe UI',
                                'font_size': 10, 'border': 1, 'align': 'left'})
            for c, v in enumerate(df_exp.columns):
                ws.write(0, c, v, hf)
            for r in range(len(df_exp)):
                for c in range(len(df_exp.columns)):
                    val = df_exp.iloc[r, c]
                    if isinstance(val, (int, float)):
                        ws.write_number(r+1, c, val, cf)
                    else:
                        ws.write(r+1, c, str(val) if pd.notnull(val) else "", cf)
        st.download_button("💾 Download Excel", output.getvalue(),
                           file_name=f"EIMS_Export_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ============================================================
# TAB 2: Import Engineering Reports
# ============================================================
elif menu == "📥 Import Engineering Reports":
    admin_password = st.sidebar.text_input("🔐 Admin Password:", type="password")
    if admin_password != CONFIG['ADMIN_PASSWORD']:
        st.warning("This page is reserved for the system administrator. Please enter the correct password.")
        st.stop()

    st.markdown("<h1 style='color: #0284c7;'>📥 Advanced Technical Reports Import Engine</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color: #94a3b8; margin-top: -10px;'>Upload structured CSV files to import daily progress data into the cloud database.</p>", unsafe_allow_html=True)

    # Database admin panel
    with st.expander("🗄️ Database Administration"):
        try:
            records = load_data()
            df = pd.DataFrame(records)
            if not df.empty:
                st.markdown("#### Delete Single Record")
                sel_id = st.selectbox("Select record to delete:", df['id'].unique(), key="admin_del")
                if st.button("Delete", key="admin_del_btn"):
                    if delete_record(sel_id):
                        log_action('delete', 'master_registry', sel_id, {'note': 'Manual delete via UI'}, performed_by='admin_ui')
                        st.success("✓ Deleted")
                        st.rerun()
                st.markdown("#### Bulk Delete")
                ids = st.multiselect("Select multiple:", df['id'].unique(), key="bulk")
                if ids and st.button(f"Delete {len(ids)} records"):
                    for i in ids:
                        delete_record(i)
                    log_action('bulk_delete', 'master_registry', None, {'ids': ids}, performed_by='admin_ui')
                    st.success(f"✓ Deleted {len(ids)}")
                    st.rerun()
            else:
                st.info("Database is empty.")
        except Exception as e:
            st.error(f"Error: {e}")

    # CSV Import
    st.markdown("---")
    st.markdown("### 📊 Bulk Daily Progress Import (CSV)")
    template = "Report Date,Main Category,Sub-category,Location,Stationing,Quantity Approved,Unit,PDF Attachment Name,Remarks\n2026-05-08,Road Works & Earthworks,Subgrade Layer 2,Road-02,1+000 to 1+160,160.0,m,Daily Inspection 08-05-2026.pdf,Verified successfully\n"
    st.download_button("📥 Download CSV Template", template.encode('utf-8-sig'),
                       file_name="EIMS_Daily_Progress_Template.csv", mime="text/csv")

    uploaded_csvs = st.file_uploader("Choose CSV files:", type=["csv"], accept_multiple_files=True)
    pdf_refs = st.file_uploader("(Optional) Upload referenced PDFs:", type=["pdf", "jpg", "jpeg", "png"], accept_multiple_files=True)

    if uploaded_csvs:
        if st.button("🚀 Process All Batches"):
            extracted = []
            for csv_file in uploaded_csvs:
                try:
                    df_csv = pd.read_csv(csv_file)
                    for _, row in df_csv.iterrows():
                        def safe(v, d=''): return str(v) if pd.notna(v) else d
                        try: q = float(row.get("Quantity Approved", 1.0))
                        except: q = 1.0
                        extracted.append({
                            'report_date': format_date_to_display(safe(row.get("Report Date", "2026-05-08"))),
                            'category': safe(row.get("Main Category", "General Works")),
                            'sub_category': safe(row.get("Sub-category", "Unknown Activity")),
                            'location': safe(row.get("Location", "Project Scope")),
                            'stationing': safe(row.get("Stationing", "")),
                            'quantity': q,
                            'unit': safe(row.get("Unit", "Unit")),
                            'status': "Pass",
                            'remarks': safe(row.get("Remarks", "")),
                            'csv_pdf_name': safe(row.get("PDF Attachment Name", "")),
                            'activity_detail': f"- Quick batch import from CSV [File: {csv_file.name}]\n- Reference: {safe(row.get('PDF Attachment Name', 'No file'))}"
                        })
                except Exception as e:
                    st.error(f"Error reading {csv_file.name}: {e}")
            st.session_state['parsed_records'] = extracted
            st.session_state['pdf_files_dict'] = {p.name: p.read() for p in pdf_refs} if pdf_refs else {}
            st.success(f"🎉 Extracted {len(extracted)} activities. Review below.")

    if st.session_state.get('parsed_records'):
        st.markdown("### 📋 Review Extracted Data Before Approval")
        records_to_save = []
        for idx, r in enumerate(st.session_state['parsed_records']):
            with st.expander(f"⚙️ Record #{idx+1}: {r['category']} - {r['sub_category']}", expanded=True):
                c1, c2 = st.columns(2)
                with c1:
                    p_date = st.text_input("Report Date (DD-MM-YYYY):", value=r['report_date'], key=f"d{idx}")
                    p_cat = st.selectbox("Category:",
                        ["Road Works & Earthworks", "Water Networks (Wet Utilities)", "Dry Utilities & Security",
                         "Civil Structures & Crossings", "Irrigation Networks (Wet Utilities)",
                         "Infrastructure & Drainage", "Landscaping"],
                        index=match_category_index(r['category']), key=f"c{idx}")
                    p_sub = st.text_input("Sub-category:", value=r['sub_category'], key=f"s{idx}")
                    p_loc = st.text_input("Location:", value=r['location'], key=f"l{idx}")
                    p_st = st.text_input("Stationing:", value=r.get('stationing', ''), key=f"st{idx}")
                with c2:
                    p_qty = st.number_input("Quantity:", value=float(r['quantity']), format="%.2f", key=f"q{idx}")
                    p_unit = st.text_input("Unit:", value=r['unit'], key=f"u{idx}")
                    p_status = st.selectbox("Status:", ["Pass", "Rejected"], index=0 if r['status']=="Pass" else 1, key=f"ss{idx}")
                    p_rem = st.text_area("Remarks:", value=r['remarks'], key=f"r{idx}")
                    p_act = st.text_area("Activity Detail:", value=r.get('activity_detail', ''), key=f"a{idx}")
                records_to_save.append({
                    'report_date': p_date, 'category': p_cat, 'sub_category': p_sub,
                    'location': p_loc, 'quantity': p_qty, 'unit': p_unit, 'status': p_status,
                    'remarks': p_rem, 'activity_detail': p_act, 'stationing': p_st,
                    'csv_pdf_name': r.get('csv_pdf_name')
                })

        if st.button("💾 Save All Records"):
            saved = 0
            skipped = 0
            for rec in records_to_save:
                # Idempotency check
                if db.check_duplicate(rec['report_date'], rec['sub_category'], rec['location'],
                                       rec['stationing'], rec.get('csv_pdf_name')):
                    skipped += 1
                    continue
                pdf_name = rec.get('csv_pdf_name')
                pdf_bytes = st.session_state.get('pdf_files_dict', {}).get(pdf_name) if pdf_name else None
                try:
                    save_record(
                        report_date=rec['report_date'], category=rec['category'],
                        sub_category=rec['sub_category'], location=rec['location'],
                        quantity=rec['quantity'], unit=rec['unit'], status=rec['status'],
                        remarks=rec['remarks'], activity_detail=rec.get('activity_detail'),
                        stationing=rec.get('stationing'), original_filename=pdf_name,
                        pdf_bytes=pdf_bytes
                    )
                    saved += 1
                except Exception as e:
                    st.error(f"Error saving record: {e}")
            st.success(f"✓ Saved {saved} records, skipped {skipped} duplicates.")
            if saved: st.balloons()
            st.session_state['parsed_records'] = []
            st.session_state['pdf_files_dict'] = {}


# ============================================================
# TAB 3: Cloud Status
# ============================================================
elif menu == "☁️ Cloud Status":
    st.markdown("<h1 style='color: #0284c7;'>☁️ Cloud Infrastructure Status</h1>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### 🗄️ Database")
        try:
            records = load_data()
            st.metric("Total Records", len(records))
            if records:
                df = pd.DataFrame(records)
                st.metric("Distinct Locations", df['location'].nunique())
                st.metric("Distinct Categories", df['category'].nunique())
                st.metric("Date Range", f"{df['report_date'].min()} → {df['report_date'].max()}")
        except Exception as e:
            st.error(f"DB Error: {e}")

    with c2:
        st.markdown("### 📦 Storage")
        try:
            sb = get_supabase_client()
            buckets = sb.storage.list_buckets()
            for b in buckets:
                st.markdown(f"""
                <div class="metric-card" style="margin-bottom: 1rem;">
                    <div class="metric-title">Bucket: {b.name}</div>
                    <div class="metric-val" style="font-size: 1rem;">{getattr(b, 'public', False) and '🌐 Public' or '🔒 Private'}</div>
                </div>
                """, unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Storage Error: {e}")

    st.markdown("### 🔧 Configuration")
    st.json({
        "SUPABASE_URL": CONFIG['SUPABASE_URL'],
        "PROJECT_REF": CONFIG['PROJECT_REF'],
        "POOLER_HOST": CONFIG['POOLER_HOST'],
        "BUCKET_PDFS": CONFIG['BUCKET_PDFS'],
        "BUCKET_AUDITS": CONFIG['BUCKET_AUDITS'],
        "BUCKET_CSVS": CONFIG['BUCKET_CSVS'],
    })

    st.markdown("### 🛠️ Maintenance Actions")
    if st.button("🔄 Heal Database (auto-fill missing fields)"):
        with st.spinner("Healing..."):
            n = heal_database()
            st.success(f"✓ Processed {n} records for healing")
            log_action('heal_database', 'master_registry', None, {'records_processed': n}, performed_by='admin_ui')
