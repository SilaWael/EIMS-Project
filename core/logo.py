# -*- coding: utf-8 -*-
"""
EIMS Logo Module
=================
Generates a professional text-based logo as a ReportLab Drawing.

Features:
  - Designed text logo with project name + system name
  - Color-coded shield/badge design
  - Bilingual (EN/AR) support
  - Optional custom image logo upload (png/jpg)
  - Cached in DB for persistence across sessions
"""
import os
import sqlite3
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.graphics.shapes import (
    Drawing, Rect, String, Group, Line, Polygon, Circle
)
from reportlab.graphics.renderPDF import draw

from core.logger import get_logger

log = get_logger(__name__)


# ==============================================================================
#  COLOR PALETTE
# ==============================================================================
COLOR_PRIMARY = colors.HexColor('#0284c7')     # Sky blue
COLOR_SECONDARY = colors.HexColor('#00695C')   # Teal
COLOR_ACCENT = colors.HexColor('#f59e0b')      # Amber
COLOR_DARK = colors.HexColor('#1e293b')        # Slate dark
COLOR_LIGHT = colors.HexColor('#f1f5f9')       # Slate light
COLOR_WHITE = colors.white


# ==============================================================================
#  TEXT-BASED LOGO (default)
# ==============================================================================
def create_text_logo(width=14*cm, height=4*cm, lang='en'):
    """Create a professional text-based logo as a Drawing.

    Layout:
      - Left: Shield/badge icon with "EIMS" text
      - Middle: System name + tagline
      - Right: Project info
    """
    drawing = Drawing(width, height)

    # Background rectangle (subtle)
    bg = Rect(0, 0, width, height, fillColor=COLOR_LIGHT, strokeColor=None)
    drawing.add(bg)

    # Left accent stripe (teal)
    stripe = Rect(0, 0, 0.3*cm, height, fillColor=COLOR_SECONDARY, strokeColor=None)
    drawing.add(stripe)

    # ---- Shield icon (left side) ----
    shield_x = 1.2*cm
    shield_y = height - 3.2*cm
    shield_w = 2.4*cm
    shield_h = 2.6*cm

    # Shield body (polygon)
    shield_points = [
        shield_x, shield_y + shield_h,           # top-left
        shield_x + shield_w, shield_y + shield_h, # top-right
        shield_x + shield_w, shield_y + shield_h * 0.4,  # right mid
        shield_x + shield_w/2, shield_y,          # bottom point
        shield_x, shield_y + shield_h * 0.4,      # left mid
    ]
    shield = Polygon(shield_points,
                     fillColor=COLOR_PRIMARY,
                     strokeColor=COLOR_SECONDARY,
                     strokeWidth=1.5)
    drawing.add(shield)

    # Inner shield border
    inner_points = [shield_x + 0.15*cm, shield_y + shield_h - 0.15*cm,
                    shield_x + shield_w - 0.15*cm, shield_y + shield_h - 0.15*cm,
                    shield_x + shield_w - 0.15*cm, shield_y + shield_h * 0.45,
                    shield_x + shield_w/2, shield_y + 0.15*cm,
                    shield_x + 0.15*cm, shield_y + shield_h * 0.45]
    # Draw inner border as a thin polygon (just outline)
    inner_shield = Polygon(inner_points,
                           fillColor=None,
                           strokeColor=COLOR_WHITE,
                           strokeWidth=0.8)
    drawing.add(inner_shield)

    # EIMS text on shield
    eims_text = String(shield_x + shield_w/2, shield_y + shield_h/2 - 0.3*cm,
                       "EIMS",
                       fontName='Helvetica-Bold',
                       fontSize=18,
                       fillColor=COLOR_WHITE,
                       textAnchor='middle')
    drawing.add(eims_text)

    # Small gear icon below EIMS (circle)
    gear = Circle(shield_x + shield_w/2, shield_y + 0.7*cm, 0.2*cm,
                  fillColor=COLOR_ACCENT, strokeColor=COLOR_WHITE, strokeWidth=0.5)
    drawing.add(gear)

    # ---- Middle: System name + tagline ----
    text_x = 4.2*cm

    # System title (large)
    system_title = "Engineering Information\nManagement System" if lang == 'en' \
                   else "نظام إدارة المعلومات\nالهندسية"
    title_lines = system_title.split('\n')
    for i, line in enumerate(title_lines):
        y_pos = height - 1.4*cm - i * 0.7*cm
        s = String(text_x, y_pos, line,
                   fontName='Helvetica-Bold',
                   fontSize=14,
                   fillColor=COLOR_PRIMARY,
                   textAnchor='start')
        drawing.add(s)

    # Tagline below title
    tagline_en = "Smart Engineering Information Management"
    tagline_ar = "نظام ذكي لإدارة المعلومات الهندسية"
    tagline = tagline_ar if lang == 'ar' else tagline_en
    tagline_s = String(text_x, height - 1.4*cm - len(title_lines) * 0.7*cm - 0.2*cm,
                       tagline,
                       fontName='Helvetica-Oblique',
                       fontSize=9,
                       fillColor=COLOR_DARK,
                       textAnchor='start')
    drawing.add(tagline_s)

    # Decorative line
    line_y = height - 1.4*cm - len(title_lines) * 0.7*cm - 0.6*cm
    deco_line = Line(text_x, line_y, text_x + 6*cm, line_y,
                     strokeColor=COLOR_ACCENT, strokeWidth=1.5)
    drawing.add(deco_line)

    # ---- Right: Project info block ----
    right_x = width - 4.5*cm

    # Project label
    proj_label_en = "PROJECT"
    proj_label_ar = "المشروع"
    proj_label = proj_label_ar if lang == 'ar' else proj_label_en
    drawing.add(String(right_x, height - 1.0*cm, proj_label,
                       fontName='Helvetica-Bold',
                       fontSize=8,
                       fillColor=COLOR_SECONDARY,
                       textAnchor='start'))

    # Project name
    drawing.add(String(right_x, height - 1.5*cm, "108 Villas Project",
                       fontName='Helvetica-Bold',
                       fontSize=11,
                       fillColor=COLOR_DARK,
                       textAnchor='start'))

    drawing.add(String(right_x, height - 2.0*cm, "ADHA",
                       fontName='Helvetica',
                       fontSize=10,
                       fillColor=COLOR_DARK,
                       textAnchor='start'))

    # Supervisor label
    sup_label_en = "SUPERVISION"
    sup_label_ar = "الإشراف"
    sup_label = sup_label_ar if lang == 'ar' else sup_label_en
    drawing.add(String(right_x, height - 2.7*cm, sup_label,
                       fontName='Helvetica-Bold',
                       fontSize=8,
                       fillColor=COLOR_SECONDARY,
                       textAnchor='start'))

    drawing.add(String(right_x, height - 3.2*cm, "Eng. Wael Radwan",
                       fontName='Helvetica-Bold',
                       fontSize=10,
                       fillColor=COLOR_DARK,
                       textAnchor='start'))

    # Right accent stripe
    right_stripe = Rect(width - 0.3*cm, 0, 0.3*cm, height,
                        fillColor=COLOR_ACCENT, strokeColor=None)
    drawing.add(right_stripe)

    return drawing


# ==============================================================================
#  CUSTOM IMAGE LOGO (uploaded by user)
# ==============================================================================
def save_custom_logo(logo_bytes):
    """Save a custom logo image to the database.

    Args:
        logo_bytes: PNG/JPG image bytes

    Returns:
        True on success, False on failure
    """
    if not logo_bytes:
        return False

    try:
        conn = sqlite3.connect('eims.db')
        c = conn.cursor()
        # Ensure settings table exists
        c.execute("""CREATE TABLE IF NOT EXISTS system_settings
                     (key TEXT PRIMARY KEY, value TEXT)""")
        # Store as BLOB via hex encoding (system_settings.value is TEXT)
        c.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)",
                  ('custom_logo', logo_bytes.hex() if isinstance(logo_bytes, bytes) else str(logo_bytes)))
        conn.commit()
        conn.close()
        log.info(f"Custom logo saved ({len(logo_bytes)} bytes)")
        return True
    except Exception as e:
        log.error(f"Failed to save custom logo: {e}", exc_info=True)
        return False


def get_custom_logo():
    """Retrieve custom logo bytes from database. Returns bytes or None."""
    try:
        conn = sqlite3.connect('eims.db')
        c = conn.cursor()
        c.execute("SELECT value FROM system_settings WHERE key = 'custom_logo'")
        row = c.fetchone()
        conn.close()
        if row and row[0]:
            try:
                return bytes.fromhex(row[0])
            except Exception:
                return None
        return None
    except Exception as e:
        log.error(f"Failed to read custom logo: {e}")
        return None


def delete_custom_logo():
    """Remove the custom logo from the database."""
    try:
        conn = sqlite3.connect('eims.db')
        c = conn.cursor()
        c.execute("DELETE FROM system_settings WHERE key = 'custom_logo'")
        conn.commit()
        conn.close()
        log.info("Custom logo deleted")
        return True
    except Exception as e:
        log.error(f"Failed to delete custom logo: {e}")
        return False


# ==============================================================================
#  LOGO RENDERER (used by PDF report)
# ==============================================================================
def get_logo_for_pdf(width=14*cm, height=4*cm, lang='en'):
    """Returns a Drawing or Image object suitable for inclusion in a PDF.

    Priority:
      1. Custom uploaded logo (if exists in DB)
      2. Text-based logo (default)
    """
    custom_bytes = get_custom_logo()
    if custom_bytes:
        try:
            from reportlab.platypus import Image as RLImage
            import io
            img = RLImage(io.BytesIO(custom_bytes), width=width, height=height)
            # Preserve aspect ratio
            img.drawHeight = height
            img.drawWidth = width
            return img
        except Exception as e:
            log.warning(f"Could not use custom logo, falling back to text: {e}")

    return create_text_logo(width, height, lang)


if __name__ == "__main__":
    # Test: save logo as PDF
    from reportlab.platypus import SimpleDocTemplate
    from reportlab.lib.pagesizes import A4

    output = "/tmp/test_logo.pdf"
    doc = SimpleDocTemplate(output, pagesize=A4)
    story = [create_text_logo(14*cm, 4*cm, 'en')]
    doc.build(story)
    print(f"Logo test saved to: {output}")
