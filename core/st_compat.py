# -*- coding: utf-8 -*-
"""
EIMS Streamlit compatibility helpers
=====================================
Provides a unified `full_width()` helper that returns the correct kwarg
for whichever Streamlit version is installed.

  - Streamlit >= 1.46 : use `width="stretch"`
  - Streamlit <  1.46 : use `use_container_width=True`
"""
import streamlit as st
from core.logger import get_logger

log = get_logger(__name__)


def _supports_width():
    """True if this Streamlit version supports the new `width` parameter on buttons."""
    try:
        # `width` was added to st.button in 1.46; check by inspecting signature
        import inspect
        sig = inspect.signature(st.button)
        return "width" in sig.parameters
    except Exception:
        return False


SUPPORTS_WIDTH = _supports_width()


def stretch_kwargs():
    """Return the correct kwargs dict to make a widget span the full container width.

    Usage:
        st.button("Click", **stretch_kwargs())
        st.dataframe(df, **stretch_kwargs())
    """
    if SUPPORTS_WIDTH:
        return {"width": "stretch"}
    return {"use_container_width": True}
