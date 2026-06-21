# -*- coding: utf-8 -*-
"""
EIMS PDF Archive UI
====================
A dedicated page for browsing and managing stored PDF/HTML files.

Works in two modes:
  1. Local mode: PDFs stored on filesystem (pdf_archive/) — original behavior
  2. Cloud mode: PDFs stored as BLOBs in DB — for Streamlit Cloud

Features:
  - Single-record upload (PDF + HTML)
  - Multi-file batch upload with smart filename matching
  - Browse all stored documents
  - View / Download PDF / HTML
  - Migrate existing filesystem PDFs to BLOBs (one-click)
"""
import os
import re
import streamlit as st
import pandas as pd

from core.logger import get_logger
from core.st_compat import stretch_kwargs
from core.os_compat import open_file
from database import (
    DB_NAME, ARCHIVE_DIR,
    list_records_with_blobs, get_pdf_blob, get_html_blob,
    save_pdf_blob, save_html_blob, migrate_existing_pdfs_to_blobs,
    load_data, get_conn,
)
from i18n import t

log = get_logger(__name__)


# ==============================================================================
#  SMART FILENAME MATCHING
# ==============================================================================
def _normalize_filename(name):
    """Normalize a filename for matching: lowercase, remove extensions, strip spaces."""
    if not name:
        return ""
    name = str(name).lower().strip()
    # Remove extension
    name = re.sub(r'\.(pdf|html?|jpg|jpeg|png)$', '', name)
    # Remove common prefixes like "daily inspection "
    name = re.sub(r'^(daily\s*inspection|camscanner)\s*', '', name)
    # Replace separators with space
    name = re.sub(r'[-_.\s]+', ' ', name)
    # Strip trailing dashes/numbers
    name = name.strip(' -')
    return name


def _extract_date_from_filename(filename):
    """Try to extract a date from filename like 'Daily Inspection 15-06-2026.pdf'."""
    if not filename:
        return None
    s = str(filename)
    # Try DD-MM-YYYY
    m = re.search(r'(\d{1,2})[-_](\d{1,2})[-_](\d{4})', s)
    if m:
        d, m_, y = m.groups()
        try:
            return f"{int(d):02d}-{int(m_):02d}-{y}"
        except Exception:
            pass
    # Try YYYY-MM-DD
    m = re.search(r'(\d{4})[-_](\d{1,2})[-_](\d{1,2})', s)
    if m:
        y, m_, d = m.groups()
        try:
            return f"{int(d):02d}-{int(m_):02d}-{y}"
        except Exception:
            pass
    return None


def _match_files_to_records(uploaded_files, df):
    """Smart matching of uploaded files to existing records.

    Matching priority:
      1. Exact filename match with pdf_filename column
      2. Date match: file date == record report_date
      3. Normalized filename contains record sub_category

    Returns:
        list of (file_name, file_bytes, file_type, matched_record_id, match_reason)
    """
    matches = []

    # Build lookup indexes
    by_pdf_name = {}
    by_date = {}
    for _, row in df.iterrows():
        rec_id = int(row['id'])
        if row.get('pdf_filename'):
            by_pdf_name[str(row['pdf_filename']).lower().strip()] = rec_id
        if row.get('report_date'):
            by_date.setdefault(str(row['report_date']), []).append(rec_id)

    for uploaded in uploaded_files:
        fname = uploaded.name
        fbytes = uploaded.getvalue() if hasattr(uploaded, 'getvalue') else uploaded.read()
        ext = os.path.splitext(fname)[1].lower()
        ftype = 'pdf' if ext == '.pdf' else ('html' if ext in ('.html', '.htm') else None)

        if not ftype:
            matches.append((fname, fbytes, ftype, None, 'Unsupported file type'))
            continue

        # Try exact filename match
        rec_id = by_pdf_name.get(fname.lower().strip())
        if rec_id:
            matches.append((fname, fbytes, ftype, rec_id, 'Filename match'))
            continue

        # Try date match
        file_date = _extract_date_from_filename(fname)
        if file_date and file_date in by_date:
            # Pick the first record with this date that doesn't already have a blob
            for rid in by_date[file_date]:
                existing = get_pdf_blob(rid) if ftype == 'pdf' else get_html_blob(rid)
                if not existing:
                    matches.append((fname, fbytes, ftype, rid, f'Date match ({file_date})'))
                    break
            else:
                matches.append((fname, fbytes, ftype, None, f'Date {file_date} found but all records already have blobs'))
            continue

        # No match
        matches.append((fname, fbytes, ftype, None, 'No match found'))

    return matches


# ==============================================================================
#  MAIN RENDER FUNCTION
# ==============================================================================
def render_pdf_archive(lang='en'):
    """Renders the PDF archive management page."""
    st.markdown(f"<h1 style='color:#0284c7;'>\U0001F4C1 {t('archive.title', lang)}</h1>", unsafe_allow_html=True)
    st.markdown(f"<p style='color:#94a3b8; margin-top:-10px;'>{t('archive.subtitle', lang)}</p>", unsafe_allow_html=True)

    # ----- Migration tool: filesystem -> BLOBs -----
    render_migration_tool(lang)

    st.markdown("---")

    # ----- Multi-file batch upload (NEW!) -----
    render_batch_upload(lang)

    st.markdown("---")

    # ----- Upload PDF/HTML to existing records (single) -----
    render_upload_to_record(lang)

    st.markdown("---")

    # ----- Browse stored PDFs -----
    render_browse_pdfs(lang)


def render_migration_tool(lang='en'):
    """One-click migration of filesystem PDFs to BLOB storage."""
    with st.expander(f"\U0001F504 {t('archive.migration_title', lang)}", expanded=False):
        st.info(t('archive.migration_hint', lang))

        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM master_registry WHERE pdf_path IS NOT NULL AND pdf_blob IS NULL"
            ).fetchone()
            needs_migration = row[0] if row else 0

            row2 = conn.execute(
                "SELECT COUNT(*) FROM master_registry WHERE pdf_blob IS NOT NULL"
            ).fetchone()
            already_blobs = row2[0] if row2 else 0
        finally:
            conn.close()

        col1, col2 = st.columns(2)
        with col1:
            st.metric(t('archive.needs_migration', lang), needs_migration)
        with col2:
            st.metric(t('archive.already_blobs', lang), already_blobs)

        if needs_migration > 0:
            if st.button(
                f"\U0001F504 {t('archive.migrate_btn', lang)} ({needs_migration})",
                **stretch_kwargs()
            ):
                with st.spinner(t('archive.migrating', lang)):
                    migrated = migrate_existing_pdfs_to_blobs()
                st.success(f"{t('archive.migration_done', lang)}: {migrated}")
                st.rerun()
        else:
            st.success(t('archive.no_migration_needed', lang))


def render_batch_upload(lang='en'):
    """Multi-file batch upload with smart matching — THE KEY NEW FEATURE."""
    with st.expander(f"\U0001F4E4 \U0001F501 {t('archive.batch_title', lang)}", expanded=True):
        st.info(t('archive.batch_hint', lang))

        # Multi-file uploader
        uploaded_files = st.file_uploader(
            t('archive.select_files', lang),
            type=["pdf", "html", "htm"],
            accept_multiple_files=True,
            key="batch_upload_files",
            label_visibility="collapsed",
        )

        if uploaded_files:
            st.info(f"{t('archive.files_selected', lang)}: {len(uploaded_files)}")

            # Load records for matching
            df = load_data(lang=lang)
            if df.empty:
                st.warning(t('archive.no_records', lang))
                return

            # Match files
            with st.spinner(t('archive.matching', lang)):
                matches = _match_files_to_records(uploaded_files, df)

            # Show match results
            st.markdown(f"#### {t('archive.match_results', lang)}")

            match_data = []
            matched_count = 0
            for fname, fbytes, ftype, rec_id, reason in matches:
                status = f"✅ #{rec_id}" if rec_id else "❌"
                match_data.append({
                    t('archive.col_file', lang): fname,
                    t('archive.col_type', lang): ftype.upper() if ftype else '?',
                    t('archive.col_size', lang): f"{len(fbytes) / 1024:.1f} KB",
                    t('archive.col_match', lang): status,
                    t('archive.col_reason', lang): reason,
                })
                if rec_id:
                    matched_count += 1

            st.dataframe(pd.DataFrame(match_data), **stretch_kwargs(), hide_index=True)

            # Summary
            st.markdown(f"**{t('archive.matched', lang)}:** {matched_count} / {len(matches)}")

            # Save button
            if matched_count > 0:
                if st.button(
                    f"\U0001F4BE {t('archive.save_all', lang)} ({matched_count})",
                    **stretch_kwargs()
                ):
                    saved = 0
                    progress = st.progress(0, text=t('archive.saving', lang))
                    for i, (fname, fbytes, ftype, rec_id, reason) in enumerate(matches):
                        if rec_id and fbytes:
                            if ftype == 'pdf':
                                if save_pdf_blob(rec_id, fbytes):
                                    saved += 1
                            elif ftype == 'html':
                                if save_html_blob(rec_id, fbytes):
                                    saved += 1
                        progress.progress((i + 1) / len(matches), text=t('archive.saving', lang))

                    st.success(f"{t('archive.saved', lang)}: {saved} / {matched_count}")
                    st.balloons()
                    st.rerun()

            # Show unmatched files info
            unmatched = [m for m in matches if not m[3]]
            if unmatched:
                with st.expander(f"⚠️ {t('archive.unmatched_title', lang)} ({len(unmatched)})"):
                    st.markdown(t('archive.unmatched_hint', lang))
                    for fname, _, ftype, _, reason in unmatched:
                        st.markdown(f"- **{fname}** — {reason}")


def render_upload_to_record(lang='en'):
    """Upload PDF/HTML files to attach to existing records (single record mode)."""
    with st.expander(f"\U0001F4E4 {t('archive.upload_title', lang)}", expanded=False):
        st.info(t('archive.upload_hint', lang))

        df = load_data(lang=lang)
        if df.empty:
            st.warning(t('archive.no_records', lang))
            return

        record_options = [
            f"#{row['id']} - {row.get('sub_category', '')} ({row['report_date']})"
            for _, row in df.iterrows()
        ]
        selected_idx = st.selectbox(
            t('archive.select_record', lang),
            range(len(record_options)),
            format_func=lambda i: record_options[i],
        )
        selected_id = int(df.iloc[selected_idx]['id'])

        col1, col2 = st.columns(2)
        with col1:
            pdf_file = st.file_uploader(
                t('archive.upload_pdf', lang),
                type=["pdf"],
                key=f"upload_pdf_{selected_id}",
            )
            if pdf_file and st.button(t('archive.save_pdf_btn', lang), key=f"save_pdf_{selected_id}"):
                pdf_bytes = pdf_file.read()
                if save_pdf_blob(selected_id, pdf_bytes):
                    st.success(f"{t('archive.saved', lang)} ({len(pdf_bytes):,} bytes)")
                    st.rerun()
                else:
                    st.error(t('archive.save_failed', lang))

        with col2:
            html_file = st.file_uploader(
                t('archive.upload_html', lang),
                type=["html", "htm"],
                key=f"upload_html_{selected_id}",
            )
            if html_file and st.button(t('archive.save_html_btn', lang), key=f"save_html_{selected_id}"):
                html_bytes = html_file.read()
                if save_html_blob(selected_id, html_bytes):
                    st.success(f"{t('archive.saved', lang)} ({len(html_bytes):,} bytes)")
                    st.rerun()
                else:
                    st.error(t('archive.save_failed', lang))


def render_browse_pdfs(lang='en'):
    """Browse and download all stored PDFs."""
    st.markdown(f"### \U0001F4C2 {t('archive.browse_title', lang)}")

    records = list_records_with_blobs()
    if not records:
        st.info(t('archive.no_blobs', lang))
        return

    st.info(f"{t('archive.total_stored', lang)}: {len(records)}")

    summary_data = []
    for r in records:
        rec_id, date, sub_cat, filename, size, has_html = r
        summary_data.append({
            'ID': rec_id,
            t('col.date', lang): date,
            'Sub-Category': sub_cat or '',
            'PDF': filename or f'record_{rec_id}.pdf',
            'Size (KB)': f"{size / 1024:.1f}",
            'HTML': '✓' if has_html else '—',
        })

    df_summary = pd.DataFrame(summary_data)
    st.dataframe(df_summary, **stretch_kwargs(), hide_index=True)

    st.markdown(f"#### {t('archive.view_title', lang)}")
    selected_id = st.selectbox(
        t('archive.select_to_view', lang),
        [r[0] for r in records],
        format_func=lambda rid: f"#{rid} — {next((r[2] for r in records if r[0] == rid), '')}"
    )

    if selected_id:
        col1, col2, col3 = st.columns(3)

        with col1:
            pdf_bytes = get_pdf_blob(selected_id)
            if pdf_bytes:
                filename = next((r[3] for r in records if r[0] == selected_id), None) or f"record_{selected_id}.pdf"
                st.download_button(
                    label=f"\U0001F4E5 {t('archive.download_pdf', lang)}",
                    data=pdf_bytes,
                    file_name=filename,
                    mime="application/pdf",
                    **stretch_kwargs(),
                )

        with col2:
            html_bytes = get_html_blob(selected_id)
            if html_bytes:
                html_filename = f"record_{selected_id}.html"
                st.download_button(
                    label=f"\U0001F310 {t('archive.download_html', lang)}",
                    data=html_bytes,
                    file_name=html_filename,
                    mime="text/html",
                    **stretch_kwargs(),
                )
            else:
                st.info(t('archive.no_html', lang))

        with col3:
            if pdf_bytes:
                if st.button(f"\U0001F441\ufe0f {t('archive.view_in_browser', lang)}", **stretch_kwargs()):
                    try:
                        st.pdf_viewer(pdf_bytes)
                    except AttributeError:
                        import base64
                        b64 = base64.b64encode(pdf_bytes).decode()
                        st.markdown(
                            f'<iframe src="data:application/pdf;base64,{b64}" '
                            f'width="100%" height="600" type="application/pdf"></iframe>',
                            unsafe_allow_html=True,
                        )
