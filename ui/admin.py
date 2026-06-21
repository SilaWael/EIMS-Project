# -*- coding: utf-8 -*-
"""
EIMS Admin UI Components
========================
Reusable Streamlit components for:
  - Backup management (list / create / restore / delete)
  - Password change form
  - Database admin panel (uses new secure delete APIs)
"""
import os
import streamlit as st

from core.logger import get_logger
from core.backup import (
    create_backup, list_backups, restore_from_backup, delete_backup,
)
from core.st_compat import stretch_kwargs
from core.logo import save_custom_logo, get_custom_logo, delete_custom_logo, create_text_logo
from auth.auth import change_password, is_first_run
from database import (
    delete_record, delete_records_bulk, reset_database, count_records, load_data,
)
from i18n import t

log = get_logger(__name__)


# ==============================================================================
#  BACKUP MANAGER
# ==============================================================================
def render_backup_manager(lang='en'):
    """Renders the backup management UI."""
    st.markdown(f"#### \U0001F4BE {t('admin.backups', lang)}")

    col1, col2 = st.columns([1, 2])
    with col1:
        if st.button(f"\U0001F4E5 {t('admin.create_backup', lang)}", **stretch_kwargs()):
            path = create_backup("manual")
            if path:
                st.success(f"{t('admin.backup_created', lang)}: {os.path.basename(path)}")
                st.rerun()
            else:
                st.error(t('admin.backup_failed', lang))

    with col2:
        st.info(f"{t('admin.backup_hint', lang)}")

    backups = list_backups()
    if not backups:
        st.info(t('admin.no_backups', lang))
        return

    st.markdown(f"**{t('admin.available_backups', lang)}** ({len(backups)})")

    for b in backups:
        with st.expander(f"\U0001F4C2 {b['name']}  |  {b['created_at']}  |  {b['size_kb']:.1f} KB"):
            c1, c2 = st.columns(2)
            with c1:
                if st.button(f"\U0001F504 {t('admin.restore', lang)}", key=f"restore_{b['name']}", **stretch_kwargs()):
                    ok, msg = restore_from_backup(b['path'])
                    if ok:
                        st.success(msg)
                        st.warning(t('admin.restart_hint', lang))
                        log.info(f"User restored backup: {b['name']}")
                    else:
                        st.error(msg)
            with c2:
                if st.button(f"\U0001F5D1\ufe0f {t('admin.delete_backup', lang)}", key=f"delbk_{b['name']}", **stretch_kwargs()):
                    if delete_backup(b['path']):
                        st.success(t('admin.backup_deleted', lang))
                        st.rerun()


# ==============================================================================
#  LOGO MANAGER
# ==============================================================================
def render_logo_manager(lang='en'):
    """Renders the logo management UI — upload custom logo or use default text logo."""
    st.markdown(f"#### \U0001F3A8 {t('admin.logo_title', lang)}")
    st.info(t('admin.logo_hint', lang))

    # Show current logo (default text logo as preview)
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown(f"**{t('admin.logo_current', lang)}:**")
        # Try to show custom logo if exists
        custom_logo = get_custom_logo()
        if custom_logo:
            try:
                st.image(custom_logo, caption=t('admin.logo_custom', lang), use_container_width=True)
            except Exception as e:
                st.warning(f"{t('admin.logo_display_error', lang)}: {e}")
        else:
            st.info(t('admin.logo_default_text', lang))

    with col2:
        # Delete button (only if custom logo exists)
        if custom_logo:
            if st.button(f"\U0001F5D1\ufe0f {t('admin.logo_delete', lang)}", **stretch_kwargs()):
                if delete_custom_logo():
                    st.success(t('admin.logo_deleted', lang))
                    st.rerun()

    # Upload new logo
    st.markdown(f"**{t('admin.logo_upload', lang)}:**")
    uploaded_logo = st.file_uploader(
        t('admin.logo_select', lang),
        type=["png", "jpg", "jpeg"],
        key="logo_uploader",
        label_visibility="collapsed",
    )

    if uploaded_logo is not None:
        # Preview
        st.markdown(f"**{t('admin.logo_preview', lang)}:**")
        st.image(uploaded_logo, use_container_width=True)

        # Save button
        if st.button(f"\U0001F4BE {t('admin.logo_save', lang)}", **stretch_kwargs()):
            logo_bytes = uploaded_logo.read()
            if save_custom_logo(logo_bytes):
                st.success(t('admin.logo_saved', lang))
                st.balloons()
                st.rerun()
            else:
                st.error(t('admin.logo_save_failed', lang))

    # Tips
    with st.expander(f"\U0001F4A1 {t('admin.logo_tips_title', lang)}"):
        st.markdown(f"""
        **{t('admin.logo_tips', lang)}:**
        - PNG with transparent background (recommended)
        - {t('admin.logo_tips_size', lang)}: 1200×400 pixels (3:1 ratio)
        - {t('admin.logo_tips_max', lang)}: 500 KB
        - {t('admin.logo_tips_format', lang)}: PNG, JPG, JPEG
        """)


# ==============================================================================
#  PASSWORD CHANGE
# ==============================================================================
def render_password_change_form(lang='en'):
    """Renders the change-password form."""
    st.markdown(f"#### \U0001F510 {t('admin.change_password', lang)}")

    if is_first_run():
        st.warning(t('admin.first_run_warning', lang))

    with st.form("change_pwd_form", clear_on_submit=True):
        current = st.text_input(
            f"\U0001F511 {t('admin.current_password', lang)}",
            type="password"
        )
        new_pwd = st.text_input(
            f"\U0001F511 {t('admin.new_password', lang)}",
            type="password"
        )
        confirm = st.text_input(
            f"\U0001F511 {t('admin.confirm_password', lang)}",
            type="password"
        )

        submitted = st.form_submit_button(f"\U0001F4BE {t('admin.change_password_btn', lang)}")

        if submitted:
            if not current or not new_pwd or not confirm:
                st.error(t('admin.fill_all_fields', lang))
            elif new_pwd != confirm:
                st.error(t('admin.passwords_dont_match', lang))
            elif len(new_pwd) < 4:
                st.error(t('admin.password_too_short', lang))
            else:
                ok, msg = change_password(current, new_pwd)
                if ok:
                    st.success(msg)
                    log.info("Admin password changed via UI")
                else:
                    st.error(msg)


# ==============================================================================
#  DATABASE ADMIN PANEL (refactored)
# ==============================================================================
def render_database_admin_panel(lang='en'):
    """Renders the database admin panel with new secure APIs."""
    with st.expander(f"\U0001F6E0 {t('import.admin_panel', lang)}"):
        count = count_records()
        if count == 0:
            st.info(t('admin.empty_db', lang))
            return

        st.info(f"{t('admin.records_in_db', lang)}: **{count}**")

        # --- Single delete ---
        st.markdown(f"#### {t('import.delete_single', lang)}")
        df = load_data(lang=lang)
        admin_id = st.selectbox(
            t('admin.select_id', lang),
            df['id'].unique(),
            key="admin_del_id_v2"
        )
        if st.button(t('import.delete_single_btn', lang), key="admin_del_btn_v2"):
            if delete_record(admin_id):
                st.success(t('admin.deleted', lang))
                st.rerun()

        st.markdown("---")

        # --- Bulk delete ---
        st.markdown(f"#### {t('import.delete_bulk', lang)}")
        ids = st.multiselect(
            t('admin.select_ids', lang),
            df['id'].unique(),
            key="bulk_del_v2"
        )
        if ids:
            if st.button(
                f"{t('import.delete_bulk_btn', lang)} ({len(ids)})",
                key="bulk_btn_v2"
            ):
                deleted = delete_records_bulk(ids)
                st.success(f"{t('admin.deleted', lang)}: {deleted}")
                st.rerun()

        st.markdown("---")

        # --- Factory reset ---
        st.markdown(f"#### {t('import.reset', lang)}")
        st.warning(t('admin.reset_warning', lang))
        confirm = st.checkbox(
            t('import.reset_confirm', lang),
            key="reset_conf_v2"
        )
        if confirm:
            if st.button(t('import.reset_btn', lang), key="reset_btn_v2"):
                reset_database()
                st.success(t('admin.reset_done', lang))
                st.rerun()

        st.markdown("---")

        # --- Backup manager ---
        render_backup_manager(lang)

        st.markdown("---")

        # --- Logo manager ---
        render_logo_manager(lang)

        st.markdown("---")

        # --- Password change ---
        render_password_change_form(lang)
