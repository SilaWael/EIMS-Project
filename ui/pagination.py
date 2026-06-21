# -*- coding: utf-8 -*-
"""
EIMS Pagination Helper
======================
Provides a simple, reusable pagination component for Streamlit dataframes.

Usage:
    from ui.pagination import paginated_dataframe
    paginated_dataframe(df, page_size=20, key="my_table")
"""
import streamlit as st
from core.st_compat import stretch_kwargs


def paginated_dataframe(df, page_size=20, key="pagination", **kwargs):
    """Display a dataframe with pagination controls.

    Args:
        df: DataFrame to display
        page_size: number of rows per page (default 20)
        key: unique key for this pagination instance
        **kwargs: passed to st.dataframe

    Returns:
        None
    """
    if df is None or df.empty:
        st.info("No data to display.")
        return

    total_rows = len(df)
    total_pages = max(1, (total_rows + page_size - 1) // page_size)

    # Initialize current page in session state
    page_key = f"{key}_current_page"
    if page_key not in st.session_state:
        st.session_state[page_key] = 1

    # Clamp current page to valid range
    if st.session_state[page_key] > total_pages:
        st.session_state[page_key] = total_pages
    if st.session_state[page_key] < 1:
        st.session_state[page_key] = 1

    current_page = st.session_state[page_key]

    # Calculate slice
    start_idx = (current_page - 1) * page_size
    end_idx = min(start_idx + page_size, total_rows)
    df_page = df.iloc[start_idx:end_idx]

    # Display controls row
    ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns([1, 2, 2, 1])

    with ctrl_col1:
        if st.button("⏮ First", key=f"{key}_first", disabled=(current_page <= 1)):
            st.session_state[page_key] = 1
            st.rerun()

    with ctrl_col2:
        if st.button("◀ Previous", key=f"{key}_prev", disabled=(current_page <= 1)):
            st.session_state[page_key] = current_page - 1
            st.rerun()

    with ctrl_col3:
        st.markdown(
            f"<div style='text-align:center; padding-top:8px;'>"
            f"Page <strong>{current_page}</strong> of <strong>{total_pages}</strong>"
            f" &nbsp;|&nbsp; Rows <strong>{start_idx + 1}-{end_idx}</strong> of <strong>{total_rows}</strong>"
            f"</div>",
            unsafe_allow_html=True,
        )

    with ctrl_col4:
        if st.button("Next ▶", key=f"{key}_next", disabled=(current_page >= total_pages)):
            st.session_state[page_key] = current_page + 1
            st.rerun()

    # Page size selector
    size_col1, size_col2 = st.columns([3, 1])
    with size_col2:
        size_options = [10, 20, 50, 100, 200]
        try:
            default_idx = size_options.index(page_size)
        except ValueError:
            default_idx = 1
        new_size = st.selectbox(
            "Rows per page",
            options=size_options,
            index=default_idx,
            key=f"{key}_size",
            label_visibility="collapsed",
        )
        if new_size != page_size:
            page_size = new_size
            st.rerun()

    # Display the dataframe page
    st.dataframe(df_page, **stretch_kwargs(), hide_index=True, **kwargs)
