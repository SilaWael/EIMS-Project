# -*- coding: utf-8 -*-
"""
EIMS Export Module
==================
Enhanced Excel export with multiple sheets:
  - Sheet 1: Master Registry (full data with bilingual labels)
  - Sheet 2: Summary by Discipline (pivot)
  - Sheet 3: Summary by Road (pivot)
  - Sheet 4: Monthly Trends (pivot)
  - Sheet 5: Filtered View (current filters applied)

Styling: professional header, alternating rows, frozen panes, auto-width.
"""
import io
import pandas as pd
import xlsxwriter

from core.logger import get_logger

log = get_logger(__name__)


# ==============================================================================
#  CONSTANTS
# ==============================================================================
HEADER_BG = '#00695C'
HEADER_FG = '#FFFFFF'
ROW_ALT_BG = '#F1F5F9'
BORDER_COLOR = '#CBD5E1'

FONT_NAME = 'Segoe UI'
HEADER_FONT_SIZE = 11
CELL_FONT_SIZE = 10


# ==============================================================================
#  BUILD DATAFRAMES FOR EACH SHEET
# ==============================================================================
def _build_master_sheet(df, lang='en'):
    """Builds the master registry DataFrame with friendly column names."""
    disc_col = 'discipline_en' if lang == 'en' else 'discipline_ar'
    sys_col = 'system_en' if lang == 'en' else 'system_ar'
    comp_col = 'component_en' if lang == 'en' else 'component_ar'
    wt_col = 'work_type_en' if lang == 'en' else 'work_type_ar'
    seg_col = 'segment_en' if lang == 'en' else 'segment_ar'

    columns_map_en = {
        'id': 'ID',
        'report_date': 'Report Date',
        disc_col: 'Discipline',
        sys_col: 'System',
        comp_col: 'Component',
        wt_col: 'Work Type',
        'road_code': 'Road',
        seg_col: 'Segment',
        'stationing': 'Stationing',
        'quantity': 'Quantity',
        'unit': 'Unit',
        'status': 'Status',
        'remarks': 'Remarks',
        'pdf_filename': 'PDF Reference',
    }
    columns_map_ar = {
        'id': 'الرقم',
        'report_date': 'تاريخ التقرير',
        disc_col: 'التخصص',
        sys_col: 'النظام',
        comp_col: 'المكوّن',
        wt_col: 'نوع العمل',
        'road_code': 'الطريق',
        seg_col: 'القطاع',
        'stationing': 'التتريس',
        'quantity': 'الكمية',
        'unit': 'الوحدة',
        'status': 'الحالة',
        'remarks': 'ملاحظات',
        'pdf_filename': 'مرجع PDF',
    }
    columns_map = columns_map_ar if lang == 'ar' else columns_map_en

    # Select and rename columns
    available = [c for c in columns_map.keys() if c in df.columns]
    df_out = df[available].copy()
    df_out = df_out.rename(columns=columns_map)

    # Replace NaN with empty string for text columns
    for col in df_out.columns:
        if df_out[col].dtype == 'object':
            df_out[col] = df_out[col].fillna('').astype(str).replace('nan', '')

    return df_out


def _build_discipline_summary(df, lang='en'):
    """Summary by discipline: count, total qty, % of total."""
    disc_col = 'discipline_en' if lang == 'en' else 'discipline_ar'
    if disc_col not in df.columns:
        return pd.DataFrame()

    grouped = df.groupby(disc_col).agg(
        records=('id', 'count'),
        total_qty=('quantity', 'sum'),
    ).reset_index()
    total = grouped['total_qty'].sum()
    grouped['percentage'] = (grouped['total_qty'] / total * 100).round(1) if total > 0 else 0
    grouped = grouped.sort_values('total_qty', ascending=False)

    if lang == 'ar':
        grouped.columns = ['التخصص', 'عدد السجلات', 'إجمالي الكمية (م)', 'النسبة المئوية (%)']
    else:
        grouped.columns = ['Discipline', 'Records Count', 'Total Quantity (m)', 'Percentage (%)']

    return grouped


def _build_road_summary(df, lang='en'):
    """Summary by road: count, total qty, disciplines count."""
    if 'road_code' not in df.columns:
        return pd.DataFrame()

    df_roads = df.dropna(subset=['road_code'])
    if df_roads.empty:
        return pd.DataFrame()

    disc_col = 'discipline_en' if lang == 'en' else 'discipline_ar'

    grouped = df_roads.groupby('road_code').agg(
        records=('id', 'count'),
        total_qty=('quantity', 'sum'),
        disciplines=(disc_col, 'nunique') if disc_col in df_roads.columns else ('id', 'count'),
    ).reset_index()
    grouped = grouped.sort_values('total_qty', ascending=False)

    if lang == 'ar':
        grouped.columns = ['الطريق', 'عدد السجلات', 'إجمالي الكمية (م)', 'عدد التخصصات']
    else:
        grouped.columns = ['Road', 'Records Count', 'Total Quantity (m)', 'Disciplines Count']

    return grouped


def _build_monthly_summary(df, lang='en'):
    """Monthly pivot: rows = months, columns = disciplines."""
    disc_col = 'discipline_en' if lang == 'en' else 'discipline_ar'
    if disc_col not in df.columns:
        return pd.DataFrame()

    df_local = df.copy()
    df_local['date_parsed'] = pd.to_datetime(df_local['report_date'], format='%d-%m-%Y', errors='coerce')
    df_local = df_local.dropna(subset=['date_parsed'])
    if df_local.empty:
        return pd.DataFrame()

    df_local['month'] = df_local['date_parsed'].dt.strftime('%Y-%m')
    pivot = df_local.pivot_table(
        index='month',
        columns=disc_col,
        values='quantity',
        aggfunc='sum',
        fill_value=0,
    ).reset_index()
    pivot['Total'] = pivot.select_dtypes(include='number').sum(axis=1)
    pivot = pivot.sort_values('month')

    month_label = 'الشهر' if lang == 'ar' else 'Month'
    total_label = 'الإجمالي' if lang == 'ar' else 'Total'
    pivot = pivot.rename(columns={'month': month_label})
    if 'Total' in pivot.columns:
        pivot = pivot.rename(columns={'Total': total_label})

    return pivot


# ==============================================================================
#  EXCEL WRITER (with styling)
# ==============================================================================
def export_to_excel(df, lang='en', sheet_name_prefix='EIMS'):
    """Generates a styled multi-sheet Excel file.

    Args:
        df: full DataFrame from load_data()
        lang: 'en' or 'ar'
        sheet_name_prefix: prefix for sheet names (max 31 chars total per sheet)

    Returns:
        bytes: the Excel file content
    """
    if df.empty:
        log.warning("Export called with empty DataFrame")
        return b''

    output = io.BytesIO()

    try:
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            workbook = writer.book

            # Format definitions
            header_format = workbook.add_format({
                'bold': True, 'text_wrap': True, 'valign': 'vcenter',
                'fg_color': HEADER_BG, 'font_color': HEADER_FG,
                'border': 1, 'border_color': BORDER_COLOR,
                'font_name': FONT_NAME, 'font_size': HEADER_FONT_SIZE,
                'align': 'center',
            })
            cell_format = workbook.add_format({
                'valign': 'vcenter', 'font_name': FONT_NAME, 'font_size': CELL_FONT_SIZE,
                'border': 1, 'border_color': BORDER_COLOR, 'align': 'left',
                'text_wrap': False,
            })
            cell_alt_format = workbook.add_format({
                'valign': 'vcenter', 'font_name': FONT_NAME, 'font_size': CELL_FONT_SIZE,
                'border': 1, 'border_color': BORDER_COLOR, 'align': 'left',
                'bg_color': ROW_ALT_BG, 'text_wrap': False,
            })
            number_format = workbook.add_format({
                'valign': 'vcenter', 'font_name': FONT_NAME, 'font_size': CELL_FONT_SIZE,
                'border': 1, 'border_color': BORDER_COLOR, 'align': 'right',
                'num_format': '#,##0.00',
            })
            number_alt_format = workbook.add_format({
                'valign': 'vcenter', 'font_name': FONT_NAME, 'font_size': CELL_FONT_SIZE,
                'border': 1, 'border_color': BORDER_COLOR, 'align': 'right',
                'num_format': '#,##0.00', 'bg_color': ROW_ALT_BG,
            })
            int_format = workbook.add_format({
                'valign': 'vcenter', 'font_name': FONT_NAME, 'font_size': CELL_FONT_SIZE,
                'border': 1, 'border_color': BORDER_COLOR, 'align': 'right',
                'num_format': '#,##0',
            })

            # ----- Sheet 1: Master Registry -----
            master_label = 'السجل الرئيسي' if lang == 'ar' else 'Master Registry'
            df_master = _build_master_sheet(df, lang)
            df_master.to_excel(writer, sheet_name=master_label[:31], index=False, startrow=1, header=False)
            worksheet = writer.sheets[master_label[:31]]

            # Write styled header
            for col_num, value in enumerate(df_master.columns):
                worksheet.write(0, col_num, value, header_format)

            # Apply cell formatting with alternating rows
            for row_idx in range(len(df_master)):
                use_alt = row_idx % 2 == 1
                for col_idx, col_name in enumerate(df_master.columns):
                    val = df_master.iloc[row_idx, col_idx]
                    col_name_str = str(col_name)
                    # Determine if this is a numeric column
                    numeric_cols_en = ['Quantity']
                    numeric_cols_ar = ['الكمية']
                    is_numeric = col_name_str in numeric_cols_en + numeric_cols_ar

                    if is_numeric and pd.notna(val):
                        fmt = number_alt_format if use_alt else number_format
                        worksheet.write_number(row_idx + 1, col_idx, float(val), fmt)
                    else:
                        fmt = cell_alt_format if use_alt else cell_format
                        worksheet.write(row_idx + 1, col_idx, str(val) if pd.notna(val) else "", fmt)

            # Auto-width
            for i, col in enumerate(df_master.columns):
                try:
                    col_str = df_master[col].astype(str)
                    max_len = max(
                        col_str.map(len).max() if len(df_master) > 0 else 0,
                        len(str(col))
                    ) + 4
                except Exception:
                    max_len = len(str(col)) + 4
                worksheet.set_column(i, i, min(max(max_len, 10), 40))

            worksheet.freeze_panes(1, 0)
            worksheet.hide_gridlines(2)
            worksheet.autofilter(0, 0, len(df_master), len(df_master.columns) - 1)

            # ----- Sheet 2: Discipline Summary -----
            disc_label = 'ملخص التخصصات' if lang == 'ar' else 'Discipline Summary'
            df_disc = _build_discipline_summary(df, lang)
            if not df_disc.empty:
                df_disc.to_excel(writer, sheet_name=disc_label[:31], index=False, startrow=1, header=False)
                ws2 = writer.sheets[disc_label[:31]]
                for col_num, value in enumerate(df_disc.columns):
                    ws2.write(0, col_num, value, header_format)
                for row_idx in range(len(df_disc)):
                    for col_idx in range(len(df_disc.columns)):
                        val = df_disc.iloc[row_idx, col_idx]
                        fmt = number_format if isinstance(val, (int, float)) and col_idx > 0 else cell_format
                        if isinstance(val, (int, float)) and col_idx > 0:
                            ws2.write_number(row_idx + 1, col_idx, float(val), fmt)
                        else:
                            ws2.write(row_idx + 1, col_idx, str(val), cell_format)
                for i, col in enumerate(df_disc.columns):
                    try:
                        max_len = max(df_disc[col].astype(str).map(len).max() if len(df_disc) > 0 else 0, len(str(col))) + 4
                    except Exception:
                        max_len = len(str(col)) + 4
                    ws2.set_column(i, i, min(max(max_len, 12), 35))
                ws2.freeze_panes(1, 0)
                ws2.hide_gridlines(2)

            # ----- Sheet 3: Road Summary -----
            road_label = 'ملخص الطرق' if lang == 'ar' else 'Road Summary'
            df_road = _build_road_summary(df, lang)
            if not df_road.empty:
                df_road.to_excel(writer, sheet_name=road_label[:31], index=False, startrow=1, header=False)
                ws3 = writer.sheets[road_label[:31]]
                for col_num, value in enumerate(df_road.columns):
                    ws3.write(0, col_num, value, header_format)
                for row_idx in range(len(df_road)):
                    for col_idx in range(len(df_road.columns)):
                        val = df_road.iloc[row_idx, col_idx]
                        if isinstance(val, (int, float)) and col_idx > 0:
                            ws3.write_number(row_idx + 1, col_idx, float(val), number_format)
                        else:
                            ws3.write(row_idx + 1, col_idx, str(val), cell_format)
                for i, col in enumerate(df_road.columns):
                    try:
                        max_len = max(df_road[col].astype(str).map(len).max() if len(df_road) > 0 else 0, len(str(col))) + 4
                    except Exception:
                        max_len = len(str(col)) + 4
                    ws3.set_column(i, i, min(max(max_len, 12), 30))
                ws3.freeze_panes(1, 0)
                ws3.hide_gridlines(2)

            # ----- Sheet 4: Monthly Trends -----
            monthly_label = 'الاتجاهات الشهرية' if lang == 'ar' else 'Monthly Trends'
            df_monthly = _build_monthly_summary(df, lang)
            if not df_monthly.empty:
                df_monthly.to_excel(writer, sheet_name=monthly_label[:31], index=False, startrow=1, header=False)
                ws4 = writer.sheets[monthly_label[:31]]
                for col_num, value in enumerate(df_monthly.columns):
                    ws4.write(0, col_num, value, header_format)
                for row_idx in range(len(df_monthly)):
                    for col_idx in range(len(df_monthly.columns)):
                        val = df_monthly.iloc[row_idx, col_idx]
                        if isinstance(val, (int, float)) and col_idx > 0:
                            ws4.write_number(row_idx + 1, col_idx, float(val), number_format)
                        else:
                            ws4.write(row_idx + 1, col_idx, str(val), cell_format)
                for i, col in enumerate(df_monthly.columns):
                    try:
                        max_len = max(df_monthly[col].astype(str).map(len).max() if len(df_monthly) > 0 else 0, len(str(col))) + 4
                    except Exception:
                        max_len = len(str(col)) + 4
                    ws4.set_column(i, i, min(max(max_len, 12), 30))
                ws4.freeze_panes(1, 1)
                ws4.hide_gridlines(2)

        output.seek(0)
        log.info(f"Excel export generated: {len(df)} records, 4 sheets, lang={lang}")
        return output.getvalue()

    except Exception as e:
        log.error(f"Excel export failed: {e}", exc_info=True)
        return b''


# ==============================================================================
#  CSV EXPORT (simple)
# ==============================================================================
def export_to_csv(df, lang='en'):
    """Simple CSV export of the master registry."""
    df_out = _build_master_sheet(df, lang)
    return df_out.to_csv(index=False).encode('utf-8-sig')
