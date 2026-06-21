# -*- coding: utf-8 -*-
"""
EIMS - Engineering Information Management System (v2)
=====================================================
Hierarchical classification + bilingual (EN/AR) + RTL support + smart auto-classifier.

Phase 2 enhancements:
  - Modular structure (core/, ui/, auth/)
  - Proper logging (replaces silent except: pass)
  - bcrypt + pepper password security
  - Automatic backups before destructive operations

Run:  py -m streamlit run app.py
"""
import os
import re
import json
import sqlite3
from datetime import datetime

import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup

# --- Local modules ---
from core.logger import get_logger
from core.backup import create_backup, list_backups
from core.st_compat import stretch_kwargs
from core.exporter import export_to_excel, export_to_csv
from core.pdf_report import generate_progress_report
from core.os_compat import open_file
from core.template_generator import generate_excel_template, generate_csv_template
from auth.auth import init_auth, verify_admin_password, is_first_run
from database import (
    DB_NAME, ARCHIVE_DIR,
    init_db, save_setting, get_setting,
    normalize_date_to_db, format_date_to_display,
    list_disciplines, list_systems, list_components,
    list_work_types, list_stages, list_roads, list_asset_segments,
    get_class_label,
    save_record, delete_record, load_data,
)
from ui.charts import (
    chart_cumulative_timeseries, chart_distribution_donut,
    chart_roads_heatmap, chart_monthly_stacked, chart_weekly_activity,
    compute_kpis,
)
from ui.pagination import paginated_dataframe
from i18n import t, SUPPORTED_LANGS, DEFAULT_LANG, is_rtl, get_lang_direction
from migrate_v1_to_v2 import classify, extract_road, extract_segment, get_ref_id, get_component_id_by_code
from ui.admin import render_database_admin_panel
from ui.pdf_archive import render_pdf_archive

log = get_logger(__name__)


# ==============================================================================
#  INITIALIZATION
# ==============================================================================
init_db()
init_auth()
log.info("EIMS application starting up")

st.set_page_config(
    page_title="EIMS - Engineering Information Management System",
    page_icon="\U0001F6E1\ufe0f",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ==============================================================================
#  LANGUAGE STATE
# ==============================================================================
def get_lang():
    if 'lang' not in st.session_state:
        saved = get_setting('lang', DEFAULT_LANG)
        st.session_state['lang'] = saved if saved in SUPPORTED_LANGS else DEFAULT_LANG
    return st.session_state['lang']


def set_lang(lang):
    st.session_state['lang'] = lang
    save_setting('lang', lang)


LANG = get_lang()
RTL = is_rtl(LANG)


# ==============================================================================
#  CSS INJECTION (with RTL support)
# ==============================================================================
def inject_css():
    direction = get_lang_direction(LANG)
    text_align = 'right' if RTL else 'left'
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&family=Outfit:wght@300;400;600;700&display=swap');

    html, body, [class*="css"], .stMarkdown {{
        font-family: 'Cairo', 'Outfit', sans-serif;
        direction: {direction};
    }}

    .stApp {{
        direction: {direction};
    }}

    /* Headings alignment */
    h1, h2, h3, h4 {{
        text-align: {text_align};
    }}

    /* Metric Card */
    .metric-card {{
        background: linear-gradient(135deg, rgba(2, 132, 199, 0.05), rgba(0, 105, 92, 0.05));
        border: 1px solid rgba(2, 132, 199, 0.2);
        padding: 1.5rem;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        text-align: center;
        transition: transform 0.2s, box-shadow 0.2s;
    }}
    .metric-card:hover {{
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        border-color: #0284c7;
    }}
    .metric-title {{
        font-size: 0.95rem;
        opacity: 0.85;
        margin-bottom: 0.5rem;
        font-weight: 600;
    }}
    .metric-val {{
        font-size: 2rem;
        font-weight: 800;
        color: #0284c7;
    }}
    .metric-unit {{
        font-size: 1rem;
        color: #00695C;
        font-weight: 700;
        margin-{'left' if not RTL else 'right'}: 0.25rem;
    }}

    /* Detail card */
    .detail-card {{
        background-color: rgba(128, 128, 128, 0.05);
        padding: 1.5rem;
        border-radius: 8px;
        border-{'right' if not RTL else 'left'}: 4px solid #0284c7;
        margin-bottom: 1rem;
    }}

    /* Badges */
    .badge {{
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.85rem;
        font-weight: 700;
        display: inline-block;
    }}
    .badge-pass {{ background-color: rgba(16, 185, 129, 0.2); color: #10b981; }}
    .badge-fail {{ background-color: rgba(239, 68, 68, 0.2); color: #ef4848; }}
    .badge-info {{ background-color: rgba(59, 130, 246, 0.2); color: #3b82f6; }}

    /* Language selector */
    .lang-box {{
        background: rgba(2, 132, 199, 0.08);
        padding: 0.5rem;
        border-radius: 8px;
        text-align: center;
        margin-bottom: 1rem;
    }}
    </style>
    """, unsafe_allow_html=True)


inject_css()


# ==============================================================================
#  SIDEBAR
# ==============================================================================
def render_sidebar():
    # Logo
    st.sidebar.markdown(f"""
        <div style="text-align: center; padding: 1rem 0;">
            <h2 style="color: #0284c7; font-weight: 800; margin-bottom: 0;">
                \U0001F6E1\ufe0f EIMS
            </h2>
            <p style="color: #94a3b8; font-size: 0.9rem;">{t('app.subtitle', LANG)}</p>
            <hr style="border-color: rgba(226, 232, 240, 0.1); margin-top: 0.5rem;"/>
        </div>
    """, unsafe_allow_html=True)

    # Language selector
    with st.sidebar.container():
        st.markdown(f"""
            <div class="lang-box">
                <p style="margin:0; font-size:0.85rem; color:#64748b;">
                    \U0001F310 {t('nav.language', LANG)}
                </p>
            </div>
        """, unsafe_allow_html=True)
        lang_cols = st.sidebar.columns(len(SUPPORTED_LANGS))
        for i, (code, name) in enumerate(SUPPORTED_LANGS.items()):
            with lang_cols[i]:
                btn_type = "primary" if code == LANG else "secondary"
                if st.button(name, key=f"lang_btn_{code}", **stretch_kwargs(),
                             type=btn_type):
                    set_lang(code)
                    st.rerun()

    st.sidebar.markdown("<br>", unsafe_allow_html=True)

    # Navigation
    menu = st.sidebar.radio(
        f"\U0001F4AC {t('nav.menu', LANG)}",
        [f"\U0001F4CA {t('nav.dashboard', LANG)}",
         f"\U0001F4C1 {t('nav.archive', LANG)}",
         f"\U0001F4E5 {t('nav.import', LANG)}"],
        index=0
    )

    # Settings
    st.sidebar.markdown("<br>", unsafe_allow_html=True)
    with st.sidebar.expander(f"\u2699\ufe0f {t('nav.settings', LANG)}", expanded=False):
        current_custom_dir = get_setting("custom_pdf_dir", "")
        custom_pdf_dir = st.text_input(
            f"\U0001F4C1 PDF Folder:",
            value=current_custom_dir,
            placeholder="D:/MyProject/PDFs",
        )
        if custom_pdf_dir != current_custom_dir:
            save_setting("custom_pdf_dir", custom_pdf_dir.strip())
            st.success("\U0001F4BE OK")
            st.rerun()

    # Footer
    st.sidebar.markdown(f"""
        <div style="position: fixed; bottom: 10px; {'left' if not RTL else 'right'}: 10px; {'right' if not RTL else 'left'}: 10px; font-size: 0.8rem; color: #64748b; text-align: center; border-top: 1px solid rgba(226, 232, 240, 0.05); padding-top: 10px;">
            {t('app.supervisor', LANG)} <strong>Wael Radwan</strong><br>
            {t('app.project', LANG)}
        </div>
    """, unsafe_allow_html=True)

    return menu


menu = render_sidebar()


# ==============================================================================
#  DASHBOARD
# ==============================================================================
# ==============================================================================
#  ANALYTICS DASHBOARD (charts + KPIs + export)
# ==============================================================================
def render_analytics_dashboard(df):
    """Renders the analytics section: KPIs + charts + export buttons."""
    if df.empty:
        return

    with st.expander(f"\U0001F4CA {t('charts.title', LANG)}", expanded=False):
        # ----- KPI Section -----
        st.markdown(f"#### \U0001F4C8 {t('charts.kpi_title', LANG)}")
        kpis = compute_kpis(df, LANG)

        k1, k2, k3, k4, k5 = st.columns(5)
        with k1:
            st.metric(t('charts.kpi_total_records', LANG), f"{kpis.get('total_records', 0):,}")
        with k2:
            st.metric(t('charts.kpi_total_qty', LANG), f"{kpis.get('total_qty', 0):,.1f} m")
        with k3:
            st.metric(t('charts.kpi_unique_roads', LANG), f"{kpis.get('unique_roads', 0)}")
        with k4:
            st.metric(t('charts.kpi_date_range', LANG), f"{kpis.get('date_range_days', 0)}")
        with k5:
            growth = kpis.get('growth_pct', 0)
            growth_str = f"+{growth}%" if growth >= 0 else f"{growth}%"
            st.metric(t('charts.kpi_growth', LANG), growth_str,
                      delta=f"{kpis.get('last_7d_records', 0)} vs {kpis.get('prev_7d_records', 0)}")

        k6, k7, k8, k9 = st.columns(4)
        with k6:
            st.metric(t('charts.kpi_daily_avg_records', LANG), f"{kpis.get('daily_avg_records', 0):.1f}")
        with k7:
            st.metric(t('charts.kpi_daily_avg_qty', LANG), f"{kpis.get('daily_avg_qty', 0):,.1f} m")
        with k8:
            st.metric(t('charts.kpi_last_7d_records', LANG), f"{kpis.get('last_7d_records', 0)}")
        with k9:
            st.metric(t('charts.kpi_last_7d_qty', LANG), f"{kpis.get('last_7d_qty', 0):,.1f} m")

        st.markdown("---")

        # ----- Charts -----
        # Row 1: Cumulative time series (full width)
        fig_cum = chart_cumulative_timeseries(df, LANG)
        if fig_cum:
            st.plotly_chart(fig_cum, use_container_width=True)

        # Row 2: Distribution donut + Weekly activity
        c1, c2 = st.columns(2)
        with c1:
            fig_donut = chart_distribution_donut(df, LANG)
            if fig_donut:
                st.plotly_chart(fig_donut, use_container_width=True)
        with c2:
            fig_weekly = chart_weekly_activity(df, LANG)
            if fig_weekly:
                st.plotly_chart(fig_weekly, use_container_width=True)

        # Row 3: Monthly stacked + Roads heatmap
        c3, c4 = st.columns(2)
        with c3:
            fig_monthly = chart_monthly_stacked(df, LANG)
            if fig_monthly:
                st.plotly_chart(fig_monthly, use_container_width=True)
        with c4:
            fig_heat = chart_roads_heatmap(df, LANG)
            if fig_heat:
                st.plotly_chart(fig_heat, use_container_width=True)

        st.markdown("---")

        # ----- Export Section -----
        st.markdown(f"#### \U0001F4E5 {t('charts.export_excel', LANG)}")
        st.info(t('charts.export_hint', LANG))

        ec1, ec2, ec3 = st.columns(3)
        with ec1:
            excel_data = export_to_excel(df, LANG)
            if excel_data:
                filename = f"EIMS_Report_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
                st.download_button(
                    label=f"\U0001F4CA {t('charts.export_excel', LANG)}",
                    data=excel_data,
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    **stretch_kwargs(),
                )
        with ec2:
            csv_data = export_to_csv(df, LANG)
            if csv_data:
                csv_filename = f"EIMS_Report_{datetime.now().strftime('%Y-%m-%d')}.csv"
                st.download_button(
                    label=f"\U0001F4C4 {t('charts.export_csv', LANG)}",
                    data=csv_data,
                    file_name=csv_filename,
                    mime="text/csv",
                    **stretch_kwargs(),
                )
        with ec3:
            # PDF report (with KPIs)
            pdf_data = generate_progress_report(df, kpis, lang=LANG)
            if pdf_data:
                pdf_filename = f"EIMS_Report_{datetime.now().strftime('%Y-%m-%d')}.pdf"
                st.download_button(
                    label=f"\U0001F4C4 {t('charts.export_pdf', LANG)}",
                    data=pdf_data,
                    file_name=pdf_filename,
                    mime="application/pdf",
                    **stretch_kwargs(),
                )


# ==============================================================================
#  DASHBOARD
# ==============================================================================
def render_dashboard():
    st.markdown(f"<h1 style='color:#0284c7;'>\U0001F4CA {t('dash.title', LANG)}</h1>", unsafe_allow_html=True)
    st.markdown(f"<p style='color:#94a3b8; margin-top:-10px;'>{t('dash.subtitle', LANG)}</p>", unsafe_allow_html=True)

    df = load_data(lang=LANG)

    if df.empty:
        st.info(f"\U0001F44B {t('dash.empty', LANG)}")
        return

    # ----- Metric cards by discipline -----
    st.markdown(f"### \U0001F4C8 {t('dash.cumulative', LANG)}")

    disc_label_col = 'discipline_en' if LANG == 'en' else 'discipline_ar'
    seg_label_col = 'segment_en' if LANG == 'en' else 'segment_ar'

    disc_stats = df.groupby(['discipline_id', disc_label_col]).agg(
        records=('id', 'count'),
        total_qty=('quantity', 'sum')
    ).reset_index()

    cols_per_row = 3
    cols = st.columns(cols_per_row)
    for i, (_, row) in enumerate(disc_stats.iterrows()):
        with cols[i % cols_per_row]:
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-title">{row[disc_label_col]}</div>
                    <div class="metric-val">{row['total_qty']:,.1f}<span class="metric-unit"> m</span></div>
                    <div style="font-size:0.8rem; color:#64748b; margin-top:0.5rem;">{int(row['records'])} {t('dash.records', LANG)}</div>
                </div>
            """, unsafe_allow_html=True)

    # Total records card
    st.markdown(f"""
        <div class="metric-card" style="margin-top:1rem;">
            <div class="metric-title">{t('metric.total_records', LANG)}</div>
            <div class="metric-val">{len(df)}</div>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("<hr style='border-color: rgba(226, 232, 240, 0.1);'/>", unsafe_allow_html=True)

    # ----- Analytics Dashboard (collapsible) -----
    render_analytics_dashboard(df)

    st.markdown("<hr style='border-color: rgba(226, 232, 240, 0.1);'/>", unsafe_allow_html=True)

    # ----- Cascading Filters -----
    st.markdown(f"### \U0001F50D {t('dash.search', LANG)}")

    f_col1, f_col2, f_col3, f_col4 = st.columns(4)

    with f_col1:
        search_query = st.text_input(
            f"\U0001F4DD {t('dash.search', LANG)}:",
            placeholder=t('dash.search_placeholder', LANG)
        )

    with f_col2:
        unique_dates = sorted(
            [d for d in df['report_date'].unique() if d],
            key=lambda x: datetime.strptime(str(x), "%d-%m-%Y") if x else datetime.min,
            reverse=True
        )
        date_list = [t('filter.all', LANG)] + unique_dates
        sel_date = st.selectbox(f"\U0001F4C5 {t('filter.date', LANG)}", date_list)

    with f_col3:
        road_list_raw = list_roads(lang=LANG)
        road_options = [(t('filter.all', LANG), None)] + [(r[2], r[0]) for r in road_list_raw]
        sel_road_idx = st.selectbox(
            f"\U0001F6E3\ufe0f {t('filter.road', LANG)}",
            range(len(road_options)),
            format_func=lambda i: road_options[i][0]
        )
        sel_road_id = road_options[sel_road_idx][1]

    with f_col4:
        status_list = [t('filter.all', LANG)] + [s for s in df['status'].unique() if s]
        sel_status = st.selectbox(f"\U0001F6E1\ufe0f {t('filter.status', LANG)}", status_list)

    # Cascading: Discipline -> System -> Component
    f_col5, f_col6, f_col7, f_col8 = st.columns(4)

    with f_col5:
        disc_list_raw = list_disciplines(lang=LANG)
        disc_options = [(t('filter.all', LANG), None)] + [(d[2], d[0]) for d in disc_list_raw]
        sel_disc_idx = st.selectbox(
            f"\U0001F4C2 {t('filter.discipline', LANG)}",
            range(len(disc_options)),
            format_func=lambda i: disc_options[i][0]
        )
        sel_disc_id = disc_options[sel_disc_idx][1]

    with f_col6:
        if sel_disc_id:
            sys_list_raw = list_systems(sel_disc_id, lang=LANG)
            sys_options = [(t('filter.all', LANG), None)] + [(s[2], s[0]) for s in sys_list_raw]
        else:
            sys_options = [(t('filter.all', LANG), None)]
        sel_sys_idx = st.selectbox(
            f"\U0001F527 {t('filter.system', LANG)}",
            range(len(sys_options)),
            format_func=lambda i: sys_options[i][0]
        )
        sel_sys_id = sys_options[sel_sys_idx][1]

    with f_col7:
        if sel_sys_id:
            comp_list_raw = list_components(sel_sys_id, lang=LANG)
            comp_options = [(t('filter.all', LANG), None)] + [(c[2], c[0]) for c in comp_list_raw]
        else:
            comp_options = [(t('filter.all', LANG), None)]
        sel_comp_idx = st.selectbox(
            f"\U0001F529 {t('filter.component', LANG)}",
            range(len(comp_options)),
            format_func=lambda i: comp_options[i][0]
        )
        sel_comp_id = comp_options[sel_comp_idx][1]

    with f_col8:
        seg_list_raw = list_asset_segments(lang=LANG)
        seg_options = [(t('filter.all', LANG), None)] + [(s[2], s[0]) for s in seg_list_raw]
        sel_seg_idx = st.selectbox(
            f"\U0001F6E7\ufe0f {t('filter.segment', LANG)}",
            range(len(seg_options)),
            format_func=lambda i: seg_options[i][0]
        )
        sel_seg_id = seg_options[sel_seg_idx][1]

    # ----- Apply filters -----
    df_filtered = df.copy()

    if search_query:
        q = search_query.lower()
        mask = (
            df_filtered['location'].fillna('').str.lower().str.contains(q) |
            df_filtered['remarks'].fillna('').str.lower().str.contains(q) |
            df_filtered['sub_category'].fillna('').str.lower().str.contains(q) |
            df_filtered['category'].fillna('').str.lower().str.contains(q) |
            df_filtered['stationing'].fillna('').str.lower().str.contains(q) |
            df_filtered['activity_detail'].fillna('').str.lower().str.contains(q) |
            df_filtered['pdf_filename'].fillna('').str.lower().str.contains(q) |
            df_filtered.get('discipline_en', pd.Series(['']*len(df_filtered))).fillna('').str.lower().str.contains(q) |
            df_filtered.get('system_en', pd.Series(['']*len(df_filtered))).fillna('').str.lower().str.contains(q) |
            df_filtered.get('component_en', pd.Series(['']*len(df_filtered))).fillna('').str.lower().str.contains(q)
        )
        df_filtered = df_filtered[mask]

    if sel_date != t('filter.all', LANG):
        df_filtered = df_filtered[df_filtered['report_date'] == sel_date]
    if sel_disc_id:
        df_filtered = df_filtered[df_filtered['discipline_id'] == sel_disc_id]
    if sel_sys_id:
        df_filtered = df_filtered[df_filtered['system_id'] == sel_sys_id]
    if sel_comp_id:
        df_filtered = df_filtered[df_filtered['component_id'] == sel_comp_id]
    if sel_road_id:
        df_filtered = df_filtered[df_filtered['road_id'] == sel_road_id]
    if sel_seg_id:
        df_filtered = df_filtered[df_filtered['asset_segment_id'] == sel_seg_id]
    if sel_status != t('filter.all', LANG):
        df_filtered = df_filtered[df_filtered['status'] == sel_status]

    st.markdown(f"\U0001F4CA **{t('dash.found', LANG)} {len(df_filtered)}** {t('dash.records', LANG)}")

    # ----- Column visibility -----
    col_options = {
        'id': t('col.id', LANG),
        'report_date': t('col.date', LANG),
        'sub_category': t('col.description', LANG),
        'discipline_id': t('col.discipline', LANG),
        'system_id': t('col.system', LANG),
        'component_id': t('col.component', LANG),
        'road_id': t('col.road', LANG),
        'asset_segment_id': t('col.segment', LANG),
        'stationing': t('col.stationing', LANG),
        'quantity': t('col.qty', LANG),
        'unit': t('col.unit', LANG),
        'status': t('col.status', LANG),
        'remarks': t('col.remarks', LANG),
        'pdf_filename': t('col.pdf', LANG),
    }

    if 'visible_columns' not in st.session_state:
        saved = get_setting('visible_columns')
        if saved:
            try:
                loaded = json.loads(saved)
                # Filter out any columns that no longer exist in the current schema (e.g. legacy 'category')
                valid_keys = set(col_options.keys())
                st.session_state['visible_columns'] = [c for c in loaded if c in valid_keys]
                if not st.session_state['visible_columns']:
                    st.session_state['visible_columns'] = list(col_options.keys())
            except Exception:
                st.session_state['visible_columns'] = list(col_options.keys())
        else:
            st.session_state['visible_columns'] = list(col_options.keys())
    else:
        # Also sanitize the in-memory state (in case schema changed between reruns)
        valid_keys = set(col_options.keys())
        st.session_state['visible_columns'] = [c for c in st.session_state['visible_columns'] if c in valid_keys]
        if not st.session_state['visible_columns']:
            st.session_state['visible_columns'] = list(col_options.keys())

    with st.expander(f"\U0001F441\ufe0f {t('dash.customize_cols', LANG)}"):
        selected_cols = st.multiselect(
            t('dash.customize_cols', LANG),
            options=list(col_options.keys()),
            default=st.session_state['visible_columns'],
            format_func=lambda x: col_options[x],
            label_visibility="collapsed"
        )
        if selected_cols != st.session_state['visible_columns']:
            st.session_state['visible_columns'] = selected_cols
            save_setting('visible_columns', json.dumps(selected_cols))

    # ----- Display table -----
    df_display = df_filtered.copy()

    # Replace FK IDs with labels for display
    label_map = {
        'discipline_id': 'discipline_en' if LANG == 'en' else 'discipline_ar',
        'system_id': 'system_en' if LANG == 'en' else 'system_ar',
        'component_id': 'component_en' if LANG == 'en' else 'component_ar',
        'asset_segment_id': 'segment_en' if LANG == 'en' else 'segment_ar',
    }
    for fk_col, label_col in label_map.items():
        if fk_col in df_display.columns and label_col in df_display.columns:
            df_display[fk_col] = df_display[label_col]

    # Add road code
    if 'road_id' in df_display.columns and 'road_code' in df_display.columns:
        df_display['road_id'] = df_display['road_code']

    display_cols = [c for c in st.session_state['visible_columns'] if c in df_display.columns]
    if not display_cols:
        # Default visible columns (when no preference saved)
        display_cols = ['id', 'report_date', 'sub_category', 'discipline_id', 'road_id', 'stationing', 'quantity', 'unit', 'status']
    df_display = df_display[display_cols].copy()

    # Rename columns to localized labels
    rename_map = {c: col_options[c] for c in display_cols if c in col_options}
    df_display = df_display.rename(columns=rename_map)

    # Paginated display
    paginated_dataframe(df_display, page_size=20, key="main_table")

    st.markdown("<hr style='border-color: rgba(226, 232, 240, 0.1);'/>", unsafe_allow_html=True)

    # ----- Detail inspector -----
    st.markdown(f"### \U0001F50E {t('dash.inspector', LANG)}")

    if len(df_filtered) > 0:
        selected_id = st.selectbox(
            f"\U0001F449 {t('dash.select_record', LANG)}",
            df_filtered['id'].unique()
        )

        if selected_id:
            row = df[df['id'] == selected_id].iloc[0]
            disc_label = row.get('discipline_en' if LANG == 'en' else 'discipline_ar', '') or ''
            sys_label = row.get('system_en' if LANG == 'en' else 'system_ar', '') or ''
            comp_label = row.get('component_en' if LANG == 'en' else 'component_ar', '') or ''
            wt_label = row.get('work_type_en' if LANG == 'en' else 'work_type_ar', '') or ''
            seg_label = row.get('segment_en' if LANG == 'en' else 'segment_ar', '') or ''

            st.markdown(f"""
                <div class="detail-card">
                    <h4 style="margin-top:0; color:#0284c7;">
                        \U0001F4CC {t('dash.detail_card', LANG)}
                    </h4>
                    <div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:1rem;">
                        <div>
                            <p style="margin-bottom:5px;"><strong>{t('dash.execution_date', LANG)}</strong></p>
                            <p style="font-size:1.1rem; opacity:0.9;">{row['report_date']}</p>
                        </div>
                        <div>
                            <p style="margin-bottom:5px;"><strong>{t('field.discipline', LANG)}</strong></p>
                            <p style="font-size:1.1rem; opacity:0.9;">{disc_label}</p>
                        </div>
                        <div>
                            <p style="margin-bottom:5px;"><strong>{t('field.system', LANG)}</strong></p>
                            <p style="font-size:1.1rem; opacity:0.9;">{sys_label}</p>
                        </div>
                        <div>
                            <p style="margin-bottom:5px;"><strong>{t('field.component', LANG)}</strong></p>
                            <p style="font-size:1.1rem; opacity:0.9;">{comp_label}</p>
                        </div>
                        <div>
                            <p style="margin-bottom:5px;"><strong>{t('field.work_type', LANG)}</strong></p>
                            <p style="font-size:1.1rem; opacity:0.9;">{wt_label}</p>
                        </div>
                        <div>
                            <p style="margin-bottom:5px;"><strong>{t('field.road', LANG)}</strong></p>
                            <p style="font-size:1.1rem; opacity:0.9;">{row.get('road_code') or '-'}</p>
                        </div>
                        <div>
                            <p style="margin-bottom:5px;"><strong>{t('field.segment', LANG)}</strong></p>
                            <p style="font-size:1.1rem; opacity:0.9;">{seg_label}</p>
                        </div>
                        <div>
                            <p style="margin-bottom:5px;"><strong>{t('dash.location_scope', LANG)}</strong></p>
                            <p style="font-size:1.1rem; opacity:0.9;">{row.get('location', '-')}</p>
                        </div>
                        <div>
                            <p style="margin-bottom:5px;"><strong>{t('dash.total_qty', LANG)}</strong></p>
                            <p style="color:#10b981; font-size:1.2rem; font-weight:bold;">
                                {row['quantity']:.2f} {row['unit']}
                            </p>
                        </div>
                        <div>
                            <p style="margin-bottom:5px;"><strong>{t('dash.stationing', LANG)}</strong></p>
                            <p style="font-size:1.1rem; opacity:0.9;">{row.get('stationing') or '-'}</p>
                        </div>
                    </div>
                    <div style="margin-top:1rem; padding-top:1rem; border-top:1px solid rgba(128,128,128,0.2);">
                        <p style="margin-bottom:5px;"><strong>{t('dash.audit_remarks', LANG)}</strong></p>
                        <p style="opacity:0.85;">{row.get('remarks') if str(row.get('remarks', '')) != 'nan' else '-'}</p>
                    </div>
                </div>
            """, unsafe_allow_html=True)

            # PDF handling
            target_pdf_path = row.get('pdf_path')
            target_pdf_filename = row.get('pdf_filename')
            is_shared = False

            if not target_pdf_path or not os.path.exists(str(target_pdf_path)):
                conn_pdf = sqlite3.connect(DB_NAME)
                cursor_pdf = conn_pdf.cursor()
                cursor_pdf.execute("""
                    SELECT pdf_path, pdf_filename FROM master_registry
                    WHERE report_date = ? AND category = ? AND pdf_path IS NOT NULL AND pdf_path != ""
                    ORDER BY id ASC LIMIT 1
                """, (row.get('report_date'), row.get('category')))
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
                        st.info(t('dash.shared_pdf', LANG))
                    if st.button(f"\U0001F4C2 {t('dash.open_pdf', LANG)}", **stretch_kwargs()):
                        if open_file(target_pdf_path):
                            st.toast(f"\U0001F4C4 OK")
                        else:
                            st.error(f"Could not open: {target_pdf_path}")
                with c2:
                    html_filename = os.path.splitext(target_pdf_filename or '')[0] + ".html"
                    html_path = os.path.join(
                        os.path.dirname(os.path.dirname(target_pdf_path)),
                        'Processed_Audits', html_filename
                    )
                    if st.button(f"\U0001F310 {t('dash.open_html', LANG)}", **stretch_kwargs()):
                        if os.path.exists(html_path):
                            if open_file(html_path):
                                st.toast(f"\U0001F310 OK")
                            else:
                                st.error(f"Could not open: {html_path}")
                        else:
                            st.warning(f"HTML: {html_path}")
                with c3:
                    with open(target_pdf_path, "rb") as f:
                        st.download_button(
                            label=f"\U0001F4E5 {t('dash.download_pdf', LANG)}",
                            data=f,
                            file_name=target_pdf_filename,
                            mime="application/octet-stream",
                            **stretch_kwargs(),
                        )
            else:
                st.warning(t('dash.no_pdf', LANG))


# ==============================================================================
#  IMPORTER
# ==============================================================================
def render_importer():
    # Password gate — uses bcrypt-verified password (not hardcoded)
    admin_password = st.sidebar.text_input(
        f"\U0001F512 {t('import.password', LANG)}:", type="password"
    )
    if not admin_password or not verify_admin_password(admin_password):
        st.warning(t('import.password_wrong', LANG))
        if is_first_run():
            st.info(f"\U0001F4A1 Default password: 1212 (please change it after login)")
        st.stop()

    log.info("Admin logged in to importer")

    st.markdown(f"<h1 style='color:#0284c7;'>\U0001F4E5 {t('import.title', LANG)}</h1>", unsafe_allow_html=True)
    st.markdown(f"<p style='color:#94a3b8; margin-top:-10px;'>{t('import.subtitle', LANG)}</p>", unsafe_allow_html=True)

    # Admin panel (uses new secure APIs with backups + password change UI)
    render_database_admin_panel(LANG)

    if 'parsed_records' not in st.session_state:
        st.session_state['parsed_records'] = []
    if 'pdf_files_dict' not in st.session_state:
        st.session_state['pdf_files_dict'] = {}

    st.markdown(f"### \U0001F4CA {t('import.bulk', LANG)}")
    st.info(f"\U0001F4A1 {t('import.upload_hint', LANG)}")

    # Template download — two options: smart Excel + simple CSV
    st.markdown(f"#### \U0001F4C4 {t('import.template', LANG)}")
    st.markdown(f"<p style='color:#64748b; font-size:0.85rem; margin-top:-0.5rem;'>{t('import.template_hint', LANG)}</p>", unsafe_allow_html=True)

    tcol1, tcol2 = st.columns(2)
    with tcol1:
        excel_template = generate_excel_template(LANG)
        if excel_template:
            template_filename = f"EIMS_Daily_Template_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
            st.download_button(
                label=f"\U0001F4CA {t('import.template_excel', LANG)}",
                data=excel_template,
                file_name=template_filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                **stretch_kwargs(),
            )
            st.caption(t('import.template_excel_hint', LANG))

    with tcol2:
        csv_template = generate_csv_template(LANG)
        if csv_template:
            csv_filename = f"EIMS_Daily_Template_{datetime.now().strftime('%Y-%m-%d')}.csv"
            st.download_button(
                label=f"\U0001F4C4 {t('import.template_csv', LANG)}",
                data=csv_template,
                file_name=csv_filename,
                mime="text/csv",
                **stretch_kwargs(),
            )
            st.caption(t('import.template_csv_hint', LANG))

    st.markdown("---")
    st.markdown(f"#### \U0001F4E4 {t('import.upload_csv', LANG)}")
    uploaded_csvs = st.file_uploader(
        "CSV",
        type=["csv"],
        accept_multiple_files=True,
        label_visibility="collapsed"
    )

    st.markdown(f"#### \U0001F4C4 {t('import.upload_pdf', LANG)}")
    st.info(f"\U0001F4A1 {t('import.pdf_hint', LANG)}")
    pdf_refs = st.file_uploader(
        "PDF",
        type=["pdf", "jpg", "jpeg", "png"],
        accept_multiple_files=True,
        label_visibility="collapsed"
    )

    if uploaded_csvs:
        if st.button(f"\U0001F680 {t('import.process', LANG)}", **stretch_kwargs()):
            try:
                extracted = []
                for uploaded_csv in uploaded_csvs:
                    df_csv = pd.read_csv(uploaded_csv)
                    for _, row in df_csv.iterrows():
                        def safe_str(val, default=""):
                            return str(val) if pd.notna(val) else default

                        try:
                            q_val = float(row.get("Quantity", 1.0))
                        except Exception:
                            q_val = 1.0

                        desc = safe_str(row.get("Description", ""))

                        # --- AUTO-CLASSIFY if Discipline/System/Component not provided ---
                        provided_disc = safe_str(row.get("Discipline", ""))
                        provided_sys = safe_str(row.get("System", ""))
                        provided_comp = safe_str(row.get("Component", ""))
                        provided_wt = safe_str(row.get("Work Type", ""))
                        provided_stage = safe_str(row.get("Stage", ""))

                        cls = classify(desc) if desc and not provided_comp else None

                        # Resolve IDs
                        def resolve_or(cls_val, provided, table):
                            code = provided or (cls_val if cls else None)
                            return get_ref_id(table, code) if code else None

                        disc_id = resolve_or(cls[0] if cls else None, provided_disc, "ref_discipline")
                        sys_id = resolve_or(cls[1] if cls else None, provided_sys, "ref_system")
                        comp_id = None
                        comp_code = provided_comp or (cls[2] if cls else None)
                        if comp_code:
                            comp_id = get_component_id_by_code(comp_code)

                        wt_code = provided_wt or (cls[3] if cls else None)
                        wt_id = get_ref_id("ref_work_type", wt_code) if wt_code else None

                        stage_code = provided_stage or (cls[4] if cls else None)
                        stage_id = get_ref_id("ref_stage", stage_code) if stage_code else None

                        # Road ID
                        road_code = safe_str(row.get("Road ID", ""))
                        if not road_code:
                            road_code, _ = extract_road(safe_str(row.get("Location", "")))
                        road_id = get_ref_id("ref_road", road_code) if road_code else None

                        # Segment ID
                        seg_code = safe_str(row.get("Asset Segment", ""))
                        if not seg_code:
                            seg_code = extract_segment(safe_str(row.get("Location", "")))
                        seg_id = get_ref_id("ref_asset_segment", seg_code) if seg_code else None

                        # Chainage
                        ch_from = safe_str(row.get("Chainage From", ""))
                        ch_to = safe_str(row.get("Chainage To", ""))
                        if ch_from and ch_to:
                            stationing = f"{ch_from} to {ch_to}"
                        elif ch_from:
                            stationing = ch_from
                        else:
                            stationing = ""

                        extracted.append({
                            "report_date": format_date_to_display(safe_str(row.get("Report Date", datetime.now().strftime('%Y-%m-%d')))),
                            "category": "",
                            "sub_category": desc,
                            "location": safe_str(row.get("Location", "")) or f"{road_code or ''} {seg_code or ''}".strip(),
                            "quantity": q_val,
                            "unit": safe_str(row.get("Unit", "Unit")),
                            "status": "Pass",
                            "remarks": safe_str(row.get("Remarks", "")),
                            "detailed_levels": [],
                            "csv_pdf_name": safe_str(row.get("PDF Attachment Name", "")),
                            "activity_detail": f"- {desc}\n- Imported from {uploaded_csv.name}",
                            # v2 fields
                            "discipline_id": disc_id,
                            "system_id": sys_id,
                            "component_id": comp_id,
                            "work_type_id": wt_id,
                            "stage_id": stage_id,
                            "road_id": road_id,
                            "asset_segment_id": seg_id,
                            "stationing": stationing,
                        })

                st.session_state['parsed_records'] = extracted

                pdf_dict = {}
                if pdf_refs:
                    for pdf in pdf_refs:
                        pdf_dict[pdf.name] = pdf.read()
                st.session_state['pdf_files_dict'] = pdf_dict

                st.success(f"\U0001F389 {t('import.extracted', LANG)} **{len(extracted)}** {t('import.activities', LANG)}")
            except Exception as e:
                st.error(f"ERROR: {e}")

    # Editable preview
    if st.session_state.get('parsed_records'):
        st.markdown(f"### \U0001F4CB {t('import.review', LANG)}")
        st.write(t('import.review_hint', LANG))

        records_to_save = []
        for idx, r in enumerate(st.session_state['parsed_records']):
            with st.expander(f"\u2699\ufe0f #{idx+1}: {r.get('sub_category', '')} | {r.get('stationing', '-')}", expanded=True):
                c1, c2 = st.columns(2)

                with c1:
                    p_date = st.text_input(f"{t('field.date', LANG)}:", value=r['report_date'], key=f"date_{idx}")
                    p_road_code = st.text_input(f"{t('field.road', LANG)}:", value=r.get('road_code', '') if 'road_code' in r else '', key=f"road_{idx}")
                    # Auto-resolve road_id from code
                    p_road_id = get_ref_id("ref_road", p_road_code) if p_road_code else None

                    # Segment dropdown
                    seg_list = list_asset_segments(lang=LANG)
                    seg_default = 0
                    if r.get('asset_segment_id'):
                        for i, s in enumerate(seg_list):
                            if s[0] == r['asset_segment_id']:
                                seg_default = i + 1
                                break
                    seg_options = [("(none)", None)] + [(s[2], s[0]) for s in seg_list]
                    seg_idx = st.selectbox(
                        f"{t('field.segment', LANG)}:",
                        range(len(seg_options)),
                        index=seg_default,
                        format_func=lambda i: seg_options[i][0],
                        key=f"seg_{idx}"
                    )
                    p_seg_id = seg_options[seg_idx][1]

                    p_stationing = st.text_input(f"{t('field.stationing', LANG)}:", value=r.get('stationing', ''), key=f"stn_{idx}")
                    p_sub = st.text_input(f"{t('field.description', LANG)}:", value=r.get('sub_category', ''), key=f"sub_{idx}")

                with c2:
                    p_qty = st.number_input(f"{t('field.qty', LANG)}:", value=float(r['quantity']), format="%.2f", key=f"qty_{idx}")
                    p_unit = st.text_input(f"{t('field.unit', LANG)}:", value=r['unit'], key=f"unit_{idx}")
                    p_status = st.selectbox(
                        f"{t('field.status', LANG)}:",
                        ["Pass", "Rejected"],
                        index=0 if r['status'] == "Pass" else 1,
                        key=f"status_{idx}"
                    )
                    p_remarks = st.text_area(f"{t('field.remarks', LANG)}:", value=r['remarks'], key=f"rem_{idx}")
                    p_activity = st.text_area(f"{t('field.activity', LANG)}:", value=r.get('activity_detail', ''), key=f"act_{idx}")

                # Show auto-classification status
                if r.get('component_id'):
                    comp_label = get_class_label('ref_component', r['component_id'], lang=LANG)
                    st.info(f"\u2705 {t('import.auto_classified', LANG)}: {comp_label}")
                else:
                    st.warning(f"\u26A0\uFE0F {t('import.manual_review', LANG)}")

                records_to_save.append({
                    "report_date": p_date,
                    "category": "",
                    "sub_category": p_sub,
                    "location": r.get('location', ''),
                    "quantity": p_qty,
                    "unit": p_unit,
                    "status": p_status,
                    "remarks": p_remarks,
                    "detailed_levels": r.get("detailed_levels", []),
                    "stationing": p_stationing,
                    "activity_detail": p_activity,
                    "csv_pdf_name": r.get("csv_pdf_name"),
                    # v2 fields
                    "discipline_id": r.get('discipline_id'),
                    "system_id": r.get('system_id'),
                    "component_id": r.get('component_id'),
                    "work_type_id": r.get('work_type_id'),
                    "stage_id": r.get('stage_id'),
                    "road_id": p_road_id,
                    "asset_segment_id": p_seg_id,
                })

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button(f"\U0001F4BE {t('import.save_all', LANG)}"):
            saved = 0
            for rec in records_to_save:
                pdf_name = rec.get("csv_pdf_name")
                file_bytes = None
                if st.session_state.get('pdf_files_dict') and pdf_name:
                    file_bytes = st.session_state['pdf_files_dict'].get(pdf_name)
                rec['pdf_bytes'] = file_bytes
                rec['original_filename'] = pdf_name
                try:
                    if save_record(rec):
                        saved += 1
                except Exception as e:
                    st.error(f"ID {idx}: {e}")
            if saved == len(records_to_save):
                st.success(f"\U0001F389 {t('import.success', LANG)} **{saved}** {t('import.success2', LANG)}")
                st.balloons()
                st.session_state['parsed_records'] = []
                st.session_state['pdf_files_dict'] = {}
            else:
                st.warning(f"Saved {saved}/{len(records_to_save)}")


# (Old render_admin_panel was moved to ui/admin.py — see render_database_admin_panel)


# ==============================================================================
#  ROUTER
# ==============================================================================
if menu == f"\U0001F4CA {t('nav.dashboard', LANG)}":
    render_dashboard()
elif menu == f"\U0001F4C1 {t('nav.archive', LANG)}":
    render_pdf_archive(LANG)
elif menu == f"\U0001F4E5 {t('nav.import', LANG)}":
    render_importer()
