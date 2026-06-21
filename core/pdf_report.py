# -*- coding: utf-8 -*-
"""
EIMS PDF Report Generator
==========================
Generates professional PDF reports using ReportLab.

Report types:
  - Full progress report (all records or filtered)
  - Discipline-specific summary
  - Monthly progress report

Layout:
  - Cover page with project info + logo placeholder + signature block
  - Executive summary (KPIs)
  - Detailed records table
  - Discipline breakdown chart (embedded)
"""
import io
import os
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.graphics.charts.barcharts import VerticalBarChart

from core.logger import get_logger
from core.logo import get_logo_for_pdf

log = get_logger(__name__)


# ==============================================================================
#  FONT REGISTRATION (with graceful fallback)
# ==============================================================================
_fonts_registered = False

def _register_fonts():
    """Register Unicode fonts. Falls back to Helvetica if not available."""
    global _fonts_registered
    if _fonts_registered:
        # Return previously chosen fonts
        return getattr(_register_fonts, '_chosen', ('Helvetica', 'Helvetica-Bold'))

    font_paths = [
        # Linux paths
        ('NotoSans', '/usr/share/fonts/truetype/chinese/NotoSansSC-Regular.ttf'),
        ('NotoSans-Bold', '/usr/share/fonts/truetype/chinese/NotoSansSC-Bold.ttf'),
        # Windows paths
        ('SegoeUI', 'C:/Windows/Fonts/segoeui.ttf'),
        ('SegoeUI-Bold', 'C:/Windows/Fonts/segoeuib.ttf'),
    ]

    registered = {}
    for name, path in font_paths:
        if path and os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                registered[name] = True
            except Exception as e:
                log.debug(f"Could not register font {name} from {path}: {e}")

    _fonts_registered = True
    # Use registered font, or fallback to Helvetica
    if 'NotoSans' in registered and 'NotoSans-Bold' in registered:
        chosen = ('NotoSans', 'NotoSans-Bold')
    elif 'SegoeUI' in registered and 'SegoeUI-Bold' in registered:
        chosen = ('SegoeUI', 'SegoeUI-Bold')
    else:
        chosen = ('Helvetica', 'Helvetica-Bold')

    _register_fonts._chosen = chosen
    return chosen


# ==============================================================================
#  STYLES
# ==============================================================================
def _build_styles(font_name, font_bold):
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name='EIMS_Title',
        fontName=font_bold,
        fontSize=24,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#0284c7'),
        spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        name='EIMS_Subtitle',
        fontName=font_name,
        fontSize=14,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#475569'),
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name='EIMS_Heading',
        fontName=font_bold,
        fontSize=16,
        alignment=TA_LEFT,
        textColor=colors.HexColor('#0284c7'),
        spaceBefore=18,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name='EIMS_Body',
        fontName=font_name,
        fontSize=10,
        alignment=TA_LEFT,
        textColor=colors.HexColor('#1e293b'),
        leading=14,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name='EIMS_KPI_Label',
        fontName=font_name,
        fontSize=9,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#64748b'),
    ))
    styles.add(ParagraphStyle(
        name='EIMS_KPI_Value',
        fontName=font_bold,
        fontSize=14,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#0284c7'),
    ))
    styles.add(ParagraphStyle(
        name='EIMS_TableHeader',
        fontName=font_bold,
        fontSize=9,
        alignment=TA_CENTER,
        textColor=colors.white,
    ))
    styles.add(ParagraphStyle(
        name='EIMS_TableCell',
        fontName=font_name,
        fontSize=8,
        alignment=TA_LEFT,
        textColor=colors.HexColor('#1e293b'),
    ))
    styles.add(ParagraphStyle(
        name='EIMS_Signature',
        fontName=font_name,
        fontSize=10,
        alignment=TA_LEFT,
        textColor=colors.HexColor('#1e293b'),
        leading=14,
    ))
    return styles


# ==============================================================================
#  PDF BUILDER
# ==============================================================================
def generate_progress_report(df, kpis, lang='en', title=None, filters_desc=None):
    """Generate a PDF progress report.

    Args:
        df: DataFrame with the records to include
        kpis: dict from compute_kpis()
        lang: 'en' or 'ar'
        title: optional custom title
        filters_desc: optional description of applied filters

    Returns:
        bytes: PDF content
    """
    if df is None or df.empty:
        log.warning("PDF export called with empty data")
        return b''

    output = io.BytesIO()
    font_name, font_bold = _register_fonts()
    styles = _build_styles(font_name, font_bold)

    # Use landscape for better table fit
    doc = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        topMargin=1.5*cm,
        bottomMargin=1.5*cm,
        leftMargin=1.5*cm,
        rightMargin=1.5*cm,
        title=title or "EIMS Progress Report",
        author="EIMS - Engineering Information Management System",
    )

    story = []

    # ========================================================================
    # COVER / HEADER — with custom logo
    # ========================================================================
    # Add the logo (custom image if uploaded, else text-based)
    logo = get_logo_for_pdf(width=24*cm, height=5*cm, lang=lang)
    story.append(logo)
    story.append(Spacer(1, 0.5*cm))

    story.append(Paragraph(
        title or ("Engineering Progress Report" if lang == 'en' else "تقرير التقدم الهندسي"),
        styles['EIMS_Heading']
    ))

    report_date_str = datetime.now().strftime("%d-%m-%Y")
    story.append(Paragraph(
        f"<b>{'Report Date' if lang == 'en' else 'تاريخ التقرير'}:</b> {report_date_str}",
        styles['EIMS_Body']
    ))
    story.append(Paragraph(
        f"<b>{'Project' if lang == 'en' else 'المشروع'}:</b> 108 Villas Project - ADHA",
        styles['EIMS_Body']
    ))
    story.append(Paragraph(
        f"<b>{'Supervision' if lang == 'en' else 'الإشراف'}:</b> Eng. Wael Radwan",
        styles['EIMS_Body']
    ))
    if filters_desc:
        story.append(Paragraph(
            f"<b>{'Filters Applied' if lang == 'en' else 'المرشحات المطبقة'}:</b> {filters_desc}",
            styles['EIMS_Body']
        ))

    story.append(Spacer(1, 0.5*cm))

    # ========================================================================
    # EXECUTIVE SUMMARY (KPIs)
    # ========================================================================
    story.append(Paragraph(
        "Executive Summary" if lang == 'en' else "الملخص التنفيذي",
        styles['EIMS_Heading']
    ))

    kpi_data = [
        [
            Paragraph(f"{kpis.get('total_records', 0):,}", styles['EIMS_KPI_Value']),
            Paragraph(f"{kpis.get('total_qty', 0):,.1f} m", styles['EIMS_KPI_Value']),
            Paragraph(f"{kpis.get('unique_roads', 0)}", styles['EIMS_KPI_Value']),
            Paragraph(f"{kpis.get('date_range_days', 0)}", styles['EIMS_KPI_Value']),
            Paragraph(f"{kpis.get('last_7d_records', 0)}", styles['EIMS_KPI_Value']),
            Paragraph(f"+{kpis.get('growth_pct', 0)}%", styles['EIMS_KPI_Value']),
        ],
        [
            Paragraph("Total Records" if lang == 'en' else "إجمالي السجلات", styles['EIMS_KPI_Label']),
            Paragraph("Total Quantity" if lang == 'en' else "إجمالي الكمية", styles['EIMS_KPI_Label']),
            Paragraph("Active Roads" if lang == 'en' else "الطرق النشطة", styles['EIMS_KPI_Label']),
            Paragraph("Active Days" if lang == 'en' else "أيام النشاط", styles['EIMS_KPI_Label']),
            Paragraph("Last 7 Days" if lang == 'en' else "آخر 7 أيام", styles['EIMS_KPI_Label']),
            Paragraph("Weekly Growth" if lang == 'en' else "النمو الأسبوعي", styles['EIMS_KPI_Label']),
        ]
    ]
    kpi_table = Table(kpi_data, colWidths=[4*cm]*6)
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F1F5F9')),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#E0F2FE')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 0.5*cm))

    # ========================================================================
    # DISCIPLINE BREAKDOWN
    # ========================================================================
    disc_col = 'discipline_en' if lang == 'en' else 'discipline_ar'
    if disc_col in df.columns:
        story.append(Paragraph(
            "Discipline Breakdown" if lang == 'en' else "تفصيل التخصصات",
            styles['EIMS_Heading']
        ))

        disc_summary = df.groupby(disc_col).agg(
            records=('id', 'count'),
            total_qty=('quantity', 'sum'),
        ).reset_index().sort_values('total_qty', ascending=False)

        total_all = disc_summary['total_qty'].sum()
        disc_summary['percentage'] = (disc_summary['total_qty'] / total_all * 100).round(1) if total_all > 0 else 0

        header_label = "Discipline" if lang == 'en' else "التخصص"
        records_label = "Records" if lang == 'en' else "السجلات"
        qty_label = "Quantity (m)" if lang == 'en' else "الكمية (م)"
        pct_label = "Percentage" if lang == 'en' else "النسبة"

        disc_data = [[
            Paragraph(f"<b>{header_label}</b>", styles['EIMS_TableHeader']),
            Paragraph(f"<b>{records_label}</b>", styles['EIMS_TableHeader']),
            Paragraph(f"<b>{qty_label}</b>", styles['EIMS_TableHeader']),
            Paragraph(f"<b>{pct_label}</b>", styles['EIMS_TableHeader']),
        ]]

        for _, row in disc_summary.iterrows():
            disc_data.append([
                Paragraph(str(row[disc_col]), styles['EIMS_TableCell']),
                Paragraph(str(int(row['records'])), styles['EIMS_TableCell']),
                Paragraph(f"{row['total_qty']:,.1f}", styles['EIMS_TableCell']),
                Paragraph(f"{row['percentage']}%", styles['EIMS_TableCell']),
            ])

        disc_table = Table(disc_data, colWidths=[8*cm, 3*cm, 4*cm, 3*cm])
        disc_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#00695C')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F1F5F9')]),
        ]))
        story.append(disc_table)
        story.append(Spacer(1, 0.5*cm))

    # ========================================================================
    # DETAILED RECORDS TABLE (first 50 rows on cover page, rest on new page)
    # ========================================================================
    story.append(PageBreak())
    story.append(Paragraph(
        "Detailed Records" if lang == 'en' else "السجلات التفصيلية",
        styles['EIMS_Heading']
    ))
    story.append(Paragraph(
        f"<i>{'Showing' if lang == 'en' else 'عرض'} {len(df)} {'records' if lang == 'en' else 'سجل'}</i>",
        styles['EIMS_Body']
    ))
    story.append(Spacer(1, 0.3*cm))

    # Build detail table
    detail_cols = ['id', 'report_date', disc_col, 'quantity', 'unit', 'road_code', 'stationing']
    detail_cols = [c for c in detail_cols if c in df.columns]

    headers_map = {
        'id': 'ID' if lang == 'en' else 'رقم',
        'report_date': 'Date' if lang == 'en' else 'التاريخ',
        disc_col: 'Discipline' if lang == 'en' else 'التخصص',
        'quantity': 'Qty' if lang == 'en' else 'الكمية',
        'unit': 'Unit' if lang == 'en' else 'الوحدة',
        'road_code': 'Road' if lang == 'en' else 'الطريق',
        'stationing': 'Stationing' if lang == 'en' else 'التتريس',
    }

    detail_data = [[Paragraph(f"<b>{headers_map[c]}</b>", styles['EIMS_TableHeader']) for c in detail_cols]]
    for _, row in df.head(200).iterrows():  # Limit to 200 to avoid huge PDFs
        detail_data.append([
            Paragraph(str(row[c]) if pd_notna(row[c]) else '', styles['EIMS_TableCell'])
            for c in detail_cols
        ])

    # Column widths
    col_widths_map = {
        'id': 1.5*cm,
        'report_date': 2.5*cm,
        disc_col: 6*cm,
        'quantity': 2*cm,
        'unit': 1.5*cm,
        'road_code': 2*cm,
        'stationing': 5*cm,
    }
    col_widths = [col_widths_map.get(c, 3*cm) for c in detail_cols]

    detail_table = Table(detail_data, colWidths=col_widths, repeatRows=1)
    detail_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#00695C')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F1F5F9')]),
    ]))
    story.append(detail_table)

    # ========================================================================
    # SIGNATURE BLOCK (last page)
    # ========================================================================
    story.append(Spacer(1, 1*cm))
    story.append(PageBreak())

    story.append(Paragraph(
        "Approval & Signatures" if lang == 'en' else "الاعتماد والتوقيعات",
        styles['EIMS_Heading']
    ))
    story.append(Spacer(1, 1*cm))

    sig_data = [
        [
            Paragraph("<b>Prepared By</b><br/><br/><br/>_______________________<br/>Name: ____________________<br/>Date: ____________________",
                     styles['EIMS_Signature']),
            Paragraph("<b>Reviewed By</b><br/><br/><br/>_______________________<br/>Name: ____________________<br/>Date: ____________________",
                     styles['EIMS_Signature']),
            Paragraph("<b>Approved By</b><br/><br/><br/>_______________________<br/>Eng. Wael Radwan<br/>Date: ____________________",
                     styles['EIMS_Signature']),
        ]
    ]
    sig_table = Table(sig_data, colWidths=[8*cm]*3)
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FAFAFA')),
    ]))
    story.append(sig_table)

    story.append(Spacer(1, 1*cm))
    story.append(Paragraph(
        f"<i>Generated by EIMS on {report_date_str} at {datetime.now().strftime('%H:%M')}</i>",
        styles['EIMS_Body']
    ))

    # Build PDF
    doc.build(story)
    output.seek(0)
    log.info(f"PDF report generated: {len(df)} records, lang={lang}")
    return output.getvalue()


def pd_notna(val):
    """Safe check for not-na values."""
    try:
        return val is not None and str(val) != 'nan' and str(val) != 'None'
    except Exception:
        return False
