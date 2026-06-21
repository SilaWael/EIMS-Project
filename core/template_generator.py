# -*- coding: utf-8 -*-
"""
EIMS Template Generator
========================
Generates a smart Excel template for daily data entry.

Features:
  - Sheet 1: "Daily Entry" — main template with data validation dropdowns
  - Sheet 2: "Reference Lists" — all valid values (Roads, Disciplines, Systems, etc.)
  - Sheet 3: "Instructions" — bilingual guide

The dropdowns are pulled from the database reference tables, so they're
always up-to-date with the current classification.
"""
import io
import os
from datetime import datetime
import pandas as pd
import xlsxwriter

from core.logger import get_logger
from database import (
    list_disciplines, list_systems, list_components,
    list_work_types, list_stages, list_roads, list_asset_segments,
)

log = get_logger(__name__)


# ==============================================================================
#  BUILD TEMPLATE
# ==============================================================================
def generate_excel_template(lang='en'):
    """Generate a smart Excel template with dropdowns.

    Args:
        lang: 'en' or 'ar'

    Returns:
        bytes: Excel file content
    """
    output = io.BytesIO()

    try:
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        # ----- Formats -----
        header_fmt = workbook.add_format({
            'bold': True, 'text_wrap': True, 'valign': 'vcenter',
            'fg_color': '#00695C', 'font_color': '#FFFFFF',
            'border': 1, 'border_color': '#CBD5E1',
            'font_name': 'Segoe UI', 'font_size': 11, 'align': 'center',
        })
        cell_fmt = workbook.add_format({
            'valign': 'vcenter', 'font_name': 'Segoe UI', 'font_size': 10,
            'border': 1, 'border_color': '#CBD5E1', 'align': 'left',
        })
        date_fmt = workbook.add_format({
            'valign': 'vcenter', 'font_name': 'Segoe UI', 'font_size': 10,
            'border': 1, 'border_color': '#CBD5E1', 'align': 'center',
            'num_format': 'yyyy-mm-dd',
        })
        number_fmt = workbook.add_format({
            'valign': 'vcenter', 'font_name': 'Segoe UI', 'font_size': 10,
            'border': 1, 'border_color': '#CBD5E1', 'align': 'right',
            'num_format': '#,##0.00',
        })
        example_fmt = workbook.add_format({
            'valign': 'vcenter', 'font_name': 'Segoe UI', 'font_size': 10,
            'border': 1, 'border_color': '#CBD5E1', 'align': 'left',
            'bg_color': '#FEF3C7',  # light amber for examples
            'italic': True,
        })
        example_date_fmt = workbook.add_format({
            'valign': 'vcenter', 'font_name': 'Segoe UI', 'font_size': 10,
            'border': 1, 'border_color': '#CBD5E1', 'align': 'center',
            'num_format': 'yyyy-mm-dd',
            'bg_color': '#FEF3C7', 'italic': True,
        })
        example_num_fmt = workbook.add_format({
            'valign': 'vcenter', 'font_name': 'Segoe UI', 'font_size': 10,
            'border': 1, 'border_color': '#CBD5E1', 'align': 'right',
            'num_format': '#,##0.00',
            'bg_color': '#FEF3C7', 'italic': True,
        })
        title_fmt = workbook.add_format({
            'bold': True, 'font_name': 'Segoe UI', 'font_size': 16,
            'font_color': '#0284c7', 'align': 'left', 'valign': 'vcenter',
        })
        subtitle_fmt = workbook.add_format({
            'font_name': 'Segoe UI', 'font_size': 11,
            'font_color': '#64748b', 'align': 'left', 'valign': 'vcenter',
            'italic': True,
        })
        section_fmt = workbook.add_format({
            'bold': True, 'font_name': 'Segoe UI', 'font_size': 12,
            'font_color': '#0284c7', 'align': 'left', 'valign': 'vcenter',
            'bottom': 2, 'border_color': '#0284c7',
        })
        instr_fmt = workbook.add_format({
            'font_name': 'Segoe UI', 'font_size': 11,
            'font_color': '#1e293b', 'align': 'left', 'valign': 'top',
            'text_wrap': True,
        })
        instr_bold_fmt = workbook.add_format({
            'bold': True, 'font_name': 'Segoe UI', 'font_size': 11,
            'font_color': '#0284c7', 'align': 'left', 'valign': 'top',
            'text_wrap': True,
        })

        # ====================================================================
        # SHEET 1: DAILY ENTRY
        # ====================================================================
        entry_label = 'الإدخال اليومي' if lang == 'ar' else 'Daily Entry'
        ws1 = workbook.add_worksheet(entry_label)
        ws1.set_tab_color('#0284c7')
        ws1.hide_gridlines(2)
        ws1.freeze_panes(5, 0)

        # Title row
        ws1.merge_range('A1:O1', 'EIMS - Daily Progress Entry' if lang == 'en' else 'EIMS - الإدخال اليومي للتقدم', title_fmt)
        ws1.set_row(0, 28)
        ws1.merge_range('A2:O2',
            'Fill one row per activity. Yellow rows are examples — replace with your data.' if lang == 'en'
            else 'املأ صفاً واحداً لكل نشاط. الصفوف الصفراء أمثلة — استبدلها ببياناتك.',
            subtitle_fmt)
        ws1.set_row(1, 20)

        # Empty row for spacing
        ws1.set_row(2, 8)

        # Column definitions: (col_index, header_en, header_ar, width, type)
        columns = [
            (0,  'Report Date',       'تاريخ التقرير',      14, 'date'),
            (1,  'Road ID',            'رقم الطريق',         12, 'dropdown_road'),
            (2,  'Asset Segment',      'قطاع الأصل',         14, 'dropdown_segment'),
            (3,  'Description',        'الوصف',              30, 'text'),
            (4,  'Discipline',         'التخصص',             22, 'dropdown_discipline'),
            (5,  'System',             'النظام',             22, 'dropdown_system'),
            (6,  'Component',          'المكوّن',            25, 'dropdown_component'),
            (7,  'Work Type',          'نوع العمل',          18, 'dropdown_worktype'),
            (8,  'Stage',              'المرحلة',            14, 'dropdown_stage'),
            (9,  'Chainage From',      'التتريس من',         13, 'text'),
            (10, 'Chainage To',        'التتريس إلى',        13, 'text'),
            (11, 'Quantity',           'الكمية',             11, 'number'),
            (12, 'Unit',               'الوحدة',             9,  'text'),
            (13, 'PDF Attachment Name','اسم ملف PDF',        25, 'text'),
            (14, 'Remarks',            'ملاحظات',            25, 'text'),
        ]

        # Write headers (row 4, index 3 — 0-based)
        header_row = 3
        ws1.set_row(header_row, 36)
        for col_idx, header_en, header_ar, width, _ in columns:
            header = header_ar if lang == 'ar' else header_en
            ws1.write(header_row, col_idx, header, header_fmt)
            ws1.set_column(col_idx, col_idx, width)

        # ====================================================================
        # SHEET 2: REFERENCE LISTS (hidden)
        # ====================================================================
        ref_label = 'القوائم المرجعية' if lang == 'ar' else 'Reference Lists'
        ws2 = workbook.add_worksheet(ref_label)
        ws2.set_tab_color('#10b981')

        ref_header_fmt = workbook.add_format({
            'bold': True, 'font_name': 'Segoe UI', 'font_size': 11,
            'fg_color': '#0284c7', 'font_color': '#FFFFFF',
            'border': 1, 'align': 'center', 'valign': 'vcenter',
        })
        ref_cell_fmt = workbook.add_format({
            'font_name': 'Segoe UI', 'font_size': 10,
            'border': 1, 'align': 'left', 'valign': 'vcenter',
        })

        # Load reference data
        disciplines = list_disciplines(lang)
        systems = list_systems(disciplines[0][0] if disciplines else 1, lang) if disciplines else []
        components = list_components(systems[0][0] if systems else 1, lang) if systems else []
        work_types = list_work_types(lang)
        stages = list_stages(lang)
        roads = list_roads(lang)
        segments = list_asset_segments(lang)

        # Write reference lists in columns
        # Col A: Roads, Col B: Segments, Col C: Disciplines, Col D: Work Types, Col E: Stages
        # Col F: Systems (limited to first discipline), Col G: Components (limited to first system)
        ref_cols = [
            ('Roads' if lang == 'en' else 'الطرق', [r[2] for r in roads]),
            ('Segments' if lang == 'en' else 'القطاعات', [s[2] for s in segments]),
            ('Disciplines' if lang == 'en' else 'التخصصات', [d[2] for d in disciplines]),
            ('Work Types' if lang == 'en' else 'أنواع العمل', [w[2] for w in work_types]),
            ('Stages' if lang == 'en' else 'المراحل', [s[2] for s in stages]),
            ('Systems (first discipline)' if lang == 'en' else 'الأنظمة (أول تخصص)', [s[2] for s in systems]),
            ('Components (first system)' if lang == 'en' else 'المكوّنات (أول نظام)', [c[2] for c in components]),
        ]

        for col_idx, (header, values) in enumerate(ref_cols):
            ws2.write(0, col_idx, header, ref_header_fmt)
            for row_idx, val in enumerate(values, start=1):
                ws2.write(row_idx, col_idx, str(val), ref_cell_fmt)
            ws2.set_column(col_idx, col_idx, 25)

        # Hide the reference sheet (still accessible for dropdowns)
        ws2.hide()

        # ====================================================================
        # APPLY DATA VALIDATION (DROPDOWNS) ON DAILY ENTRY SHEET
        # ====================================================================
        # We need to write enough rows for daily entry (say 100 rows)
        max_data_rows = 100

        # Road dropdown (col B, index 1) — Reference Lists A2:A100
        ws1.data_validation(4, 1, 4 + max_data_rows - 1, 1, {
            'validate': 'list',
            'source': f"='{ref_label}'!$A$2:$A${len(roads) + 1}",
            'input_title': 'Road' if lang == 'en' else 'الطريق',
            'input_message': 'Select road' if lang == 'en' else 'اختر الطريق',
        })

        # Segment dropdown (col C, index 2)
        ws1.data_validation(4, 2, 4 + max_data_rows - 1, 2, {
            'validate': 'list',
            'source': f"='{ref_label}'!$B$2:$B${len(segments) + 1}",
            'input_title': 'Segment' if lang == 'en' else 'القطاع',
        })

        # Discipline dropdown (col E, index 4)
        ws1.data_validation(4, 4, 4 + max_data_rows - 1, 4, {
            'validate': 'list',
            'source': f"='{ref_label}'!$C$2:$C${len(disciplines) + 1}",
            'input_title': 'Discipline' if lang == 'en' else 'التخصص',
        })

        # Work Type dropdown (col H, index 7)
        ws1.data_validation(4, 7, 4 + max_data_rows - 1, 7, {
            'validate': 'list',
            'source': f"='{ref_label}'!$D$2:$D${len(work_types) + 1}",
            'input_title': 'Work Type' if lang == 'en' else 'نوع العمل',
        })

        # Stage dropdown (col I, index 8)
        ws1.data_validation(4, 8, 4 + max_data_rows - 1, 8, {
            'validate': 'list',
            'source': f"='{ref_label}'!$E$2:$E${len(stages) + 1}",
            'input_title': 'Stage' if lang == 'en' else 'المرحلة',
        })

        # System dropdown (col F, index 5) — note: this is limited to first discipline
        if systems:
            ws1.data_validation(4, 5, 4 + max_data_rows - 1, 5, {
                'validate': 'list',
                'source': f"='{ref_label}'!$F$2:$F${len(systems) + 1}",
                'input_title': 'System' if lang == 'en' else 'النظام',
            })

        # Component dropdown (col G, index 6) — limited to first system
        if components:
            ws1.data_validation(4, 6, 4 + max_data_rows - 1, 6, {
                'validate': 'list',
                'source': f"='{ref_label}'!$G$2:$G${len(components) + 1}",
                'input_title': 'Component' if lang == 'en' else 'المكوّن',
            })

        # Date validation (col A, index 0)
        ws1.data_validation(4, 0, 4 + max_data_rows - 1, 0, {
            'validate': 'date',
            'criteria': 'between',
            'minimum': datetime(2020, 1, 1),
            'maximum': datetime(2100, 12, 31),
            'input_title': 'Date' if lang == 'en' else 'التاريخ',
            'input_message': 'YYYY-MM-DD' if lang == 'en' else 'سنة-شهر-يوم',
        })

        # Number validation (col L, index 11) — Quantity
        ws1.data_validation(4, 11, 4 + max_data_rows - 1, 11, {
            'validate': 'decimal',
            'criteria': '>=',
            'minimum': 0,
            'input_title': 'Quantity' if lang == 'en' else 'الكمية',
        })

        # ====================================================================
        # WRITE EXAMPLE ROWS (yellow background)
        # ====================================================================
        today = datetime.now().strftime('%Y-%m-%d')

        examples_en = [
            [today, 'RD-01', 'LHS', 'Subgrade Layer 1', 'Earthworks & Formation', 'General Formation', 'Subgrade (Layer 1)', 'Compaction', 'Layer 1', '0+000', '0+120', 120.0, 'm', 'Daily Inspection.pdf', 'Approved within tolerance'],
            [today, 'RD-05', 'RHS', 'Irrigation Main Line Laying', 'Wet Utilities (Hydraulic)', 'Irrigation', 'Irrigation Main Line', 'Laying / Installation', '', '0+020', '0+150', 130.0, 'm', 'Daily Inspection.pdf', 'Pipe laid and jointed'],
            [today, 'RD-04', 'CARR', 'Telecom 2-Way Conduit', 'Dry Utilities (Electrical/Comm)', 'Telecom', 'Telecom 2-Way Conduit', 'Laying / Installation', '', '0+000', '0+090', 90.0, 'm', 'Daily Inspection.pdf', 'Conduit installed'],
        ]
        examples_ar = [
            [today, 'RD-01', 'LHS', 'Subgrade Layer 1', 'أعمال الحفر والتشكيل', 'تشكيل عام', 'الطبقة التحتية (الطبقة 1)', 'دمك', 'الطبقة 1', '0+000', '0+120', 120.0, 'م', 'Daily Inspection.pdf', 'مقبول ضمن التسامح'],
            [today, 'RD-05', 'RHS', 'Irrigation Main Line Laying', 'الشبكات الرطبة (الهيدروليكية)', 'الري', 'الخط الرئيسي للري', 'تمديد / تركيب', '', '0+020', '0+150', 130.0, 'م', 'Daily Inspection.pdf', 'تم تركيب الأنبوب'],
            [today, 'RD-04', 'CARR', 'Telecom 2-Way Conduit', 'الشبكات الجافة (كهرباء/اتصالات)', 'اتصالات', 'قناة اتصالات ثنائية', 'تمديد / تركيب', '', '0+000', '0+090', 90.0, 'م', 'Daily Inspection.pdf', 'تم تركيب القناة'],
        ]
        examples = examples_ar if lang == 'ar' else examples_en

        for row_offset, example in enumerate(examples):
            row_idx = 4 + row_offset  # start at row 5 (0-based 4)
            for col_idx, val in enumerate(example):
                col_type = columns[col_idx][4]
                if col_type == 'date':
                    # Convert string to date for proper formatting
                    try:
                        dt = datetime.strptime(str(val), '%Y-%m-%d')
                        ws1.write_datetime(row_idx, col_idx, dt, example_date_fmt)
                    except Exception:
                        ws1.write(row_idx, col_idx, str(val), example_date_fmt)
                elif col_type == 'number':
                    try:
                        ws1.write_number(row_idx, col_idx, float(val), example_num_fmt)
                    except Exception:
                        ws1.write(row_idx, col_idx, str(val), example_num_fmt)
                else:
                    ws1.write(row_idx, col_idx, str(val), example_fmt)

        # Apply empty cell formatting to remaining rows (for clean look)
        for row_idx in range(4 + len(examples), 4 + max_data_rows):
            for col_idx, _, _, _, col_type in columns:
                pass  # skip — leave empty

        # ====================================================================
        # SHEET 3: INSTRUCTIONS
        # ====================================================================
        instr_label = 'التعليمات' if lang == 'ar' else 'Instructions'
        ws3 = workbook.add_worksheet(instr_label)
        ws3.set_tab_color('#f59e0b')
        ws3.hide_gridlines(2)
        ws3.set_column(0, 0, 4)
        ws3.set_column(1, 1, 80)

        row = 0
        ws3.set_row(row, 30)
        ws3.write(row, 1, 'How to use this template' if lang == 'en' else 'كيفية استخدام هذا النموذج', title_fmt)
        row += 2

        instructions_en = [
            ('Purpose', 'This template is for daily entry of completed engineering works. Each row = one activity.'),
            ('Workflow', '1) Fill the rows with your daily work. 2) Save the file. 3) Upload it via the Importer page in EIMS.'),
            ('Required Fields', 'Report Date, Road ID, Description, Quantity, Unit. Other fields are optional but recommended.'),
            ('Dropdowns', 'Fields with arrows (▼) have dropdown menus — click to select. Use them for consistency.'),
            ('Auto-Classification', 'If you leave Discipline/System/Component empty, EIMS will auto-classify based on the Description.'),
            ('Examples', 'The yellow rows are examples — replace them with your actual data or delete them.'),
            ('Multiple Days', 'You can include multiple dates in one file. Sort by date for clarity.'),
            ('PDF Reference', 'In "PDF Attachment Name", put the filename (e.g. "Daily 15-06.pdf"). The system will link it automatically if the PDF exists in Processed_Audits or Finished PDFs folders.'),
            ('Units', 'Common units: m (meters), Unit (count), m², m³. Be consistent within each activity type.'),
            ('Chainage', 'Format: 0+000 (station+offset). Example: 1+250 means 1250m from start. Leave empty if not applicable.'),
            ('Questions?', 'Contact: Eng. Wael Radwan'),
        ]

        instructions_ar = [
            ('الهدف', 'هذا النموذج لإدخال الأعمال الهندسية المنجزة يومياً. كل صف = نشاط واحد.'),
            ('طريقة العمل', '1) املأ الصفوف بأعمالك اليومية. 2) احفظ الملف. 3) ارفعه عبر صفحة الاستيراد في EIMS.'),
            ('الحقول المطلوبة', 'تاريخ التقرير، رقم الطريق، الوصف، الكمية، الوحدة. باقي الحقول اختيارية لكن يُنصح بها.'),
            ('القوائم المنسدلة', 'الحقول التي تحتوي أسهم (▼) لها قوائم منسدلة — انقر للاختيار. استخدمها للتوحيد.'),
            ('التصنيف التلقائي', 'إذا تركت التخصص/النظام/المكوّن فارغاً، سيصنّف EIMS تلقائياً بناءً على الوصف.'),
            ('الأمثلة', 'الصفوف الصفراء أمثلة — استبدلها ببياناتك الفعلية أو احذفها.'),
            ('تعدد الأيام', 'يمكنك تضمين تواريخ متعددة في ملف واحد. رتّب حسب التاريخ للوضوح.'),
            ('مرجع PDF', 'في "اسم ملف PDF"، ضع اسم الملف (مثل "Daily 15-06.pdf"). سيربطه النظام تلقائياً إذا كان موجوداً في Processed_Audits أو Finished PDFs.'),
            ('الوحدات', 'وحدات شائعة: م (متر)، وحدة (عدد)، م²، م³. كن متجانساً داخل كل نوع نشاط.'),
            ('التتريس', 'الصيغة: 0+000 (محطة+إزاحة). مثال: 1+250 تعني 1250م من البداية. اتركه فارغاً إذا لا ينطبق.'),
            ('أسئلة؟', 'تواصل مع: م. وائل رضوان'),
        ]

        instructions = instructions_ar if lang == 'ar' else instructions_en

        for header, body in instructions:
            ws3.set_row(row, 22)
            ws3.write(row, 1, header, instr_bold_fmt)
            row += 1
            ws3.set_row(row, 36)
            ws3.write(row, 1, body, instr_fmt)
            row += 2

        # Set the Daily Entry sheet as active
        ws1.activate()

        workbook.close()
        output.seek(0)
        log.info(f"Excel template generated: lang={lang}")
        return output.getvalue()

    except Exception as e:
        log.error(f"Failed to generate Excel template: {e}", exc_info=True)
        return b''


# ==============================================================================
#  CSV TEMPLATE (simple fallback)
# ==============================================================================
def generate_csv_template(lang='en'):
    """Generate a simple CSV template (for users who prefer CSV)."""
    if lang == 'ar':
        csv = (
            "تاريخ التقرير,رقم الطريق,قطاع الأصل,الوصف,التخصص,النظام,المكوّن,نوع العمل,المرحلة,"
            "التتريس من,التتريس إلى,الكمية,الوحدة,اسم ملف PDF,ملاحظات\n"
            "2026-06-15,RD-01,LHS,Subgrade Layer 1,,,Subgrade (Layer 1),Compaction,Layer 1,0+000,0+120,120.0,m,Daily Inspection 15-06-2026.pdf,مقبول\n"
            "2026-06-15,RD-05,RHS,Irrigation Main Line Laying,,,Irrigation Main Line,Laying,,0+020,0+150,130.0,m,Daily Inspection 15-06-2026.pdf,تم التركيب\n"
            "2026-06-15,RD-04,CARR,Telecom 2-Way Conduit,,,Telecom 2-Way Conduit,Laying,,0+000,0+090,90.0,m,Daily Inspection 15-06-2026.pdf,تم التركيب\n"
        )
    else:
        csv = (
            "Report Date,Road ID,Asset Segment,Description,Discipline,System,Component,Work Type,Stage,"
            "Chainage From,Chainage To,Quantity,Unit,PDF Attachment Name,Remarks\n"
            "2026-06-15,RD-01,LHS,Subgrade Layer 1,,,Subgrade (Layer 1),Compaction,Layer 1,0+000,0+120,120.0,m,Daily Inspection 15-06-2026.pdf,Approved\n"
            "2026-06-15,RD-05,RHS,Irrigation Main Line Laying,,,Irrigation Main Line,Laying,,0+020,0+150,130.0,m,Daily Inspection 15-06-2026.pdf,Pipe laid\n"
            "2026-06-15,RD-04,CARR,Telecom 2-Way Conduit,,,Telecom 2-Way Conduit,Laying,,0+000,0+090,90.0,m,Daily Inspection 15-06-2026.pdf,Conduit installed\n"
        )
    return csv.encode('utf-8-sig')


if __name__ == "__main__":
    # Test
    data = generate_excel_template('en')
    with open('/tmp/test_template.xlsx', 'wb') as f:
        f.write(data)
    print(f"Generated: {len(data)} bytes")
