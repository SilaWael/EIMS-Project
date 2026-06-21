# -*- coding: utf-8 -*-
"""
EIMS OS Compatibility Helpers
==============================
Cross-platform replacements for Windows-only functions like `os.startfile`.

Usage:
    from core.os_compat import open_file
    open_file("/path/to/file.pdf")
"""
import os
import sys
import subprocess
import webbrowser
from core.logger import get_logger

log = get_logger(__name__)


def open_file(filepath: str) -> bool:
    """Open a file with the OS default application. Cross-platform.

    Returns True if successful, False otherwise.
    """
    if not filepath:
        log.warning("open_file called with empty path")
        return False

    if not os.path.exists(filepath):
        log.warning(f"open_file: file does not exist: {filepath}")
        return False

    try:
        if sys.platform == "win32":
            # Windows: use os.startfile (native, fast)
            os.startfile(filepath)
        elif sys.platform == "darwin":
            # macOS: use 'open' command
            subprocess.run(["open", filepath], check=True, capture_output=True)
        else:
            # Linux/Unix: try xdg-open, fallback to webbrowser
            try:
                subprocess.run(["xdg-open", filepath], check=True, capture_output=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                webbrowser.open(f"file://{os.path.abspath(filepath)}")
        log.info(f"Opened file: {filepath}")
        return True
    except Exception as e:
        log.error(f"Failed to open file {filepath}: {e}", exc_info=True)
        return False


def reveal_in_explorer(filepath: str) -> bool:
    """Reveal a file in the file manager (Windows Explorer, Finder, etc.)."""
    if not filepath or not os.path.exists(filepath):
        return False
    try:
        if sys.platform == "win32":
            subprocess.run(["explorer", "/select,", os.path.abspath(filepath)], check=False)
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", filepath], check=True, capture_output=True)
        else:
            # Linux: open the containing directory
            dir_path = os.path.dirname(filepath) or "."
            subprocess.run(["xdg-open", dir_path], check=False, capture_output=True)
        return True
    except Exception as e:
        log.error(f"Failed to reveal file {filepath}: {e}")
        return False
