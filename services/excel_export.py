import io
import os
import re
import calendar
from datetime import date
import pandas as pd
from database.db import get_db
from database.models import (
    Employee, Attendance, Overtime, Advance, Discount, Expense, ReceivedFund,
    PlantDelivery, PlantDeliveryLine, PlantSupplier, PlantItem,
)
from services.discount_service import DISCOUNT_TYPE_LABELS
from database.paths import get_downloads_dir
from services.payroll_service import calculate_payroll
from services.attendance_service import get_attendance_matrix
from services.overtime_service import get_overtime_matrix
from services.overtime_records import unique_overtime_records
from services.projects import get_current_project_id, get_project_name
from core.config import BRAND_PRIMARY_COLOR
# NOTE (Phase 4A fix): previously imported COLORS/COMPANY_NAME/COMPANY_TAGLINE
# from components.theme. Importing anything under the `components` package
# executes components/__init__.py, which also imports components.layout
# (Streamlit) and components.charts (Plotly) — so this service was, despite
# having no direct `import streamlit`, transitively NOT importable without
# Streamlit installed. That violated Phase 4A Step 9 ("excel_import.py /
# excel_export.py ... can be called from normal Python code without
# Streamlit") and Step 17 ("service layer must be importable without
# Streamlit"). Only `COLORS['primary']` was actually used below (COMPANY_NAME/
# COMPANY_TAGLINE were imported but unused), so this now reads the one color
# it needs from core.config, the shared Streamlit-free source of truth.


def export_full_report(month: int, year: int, project_id: int = None) -> bytes:
    """Generate full Excel report workbook, scoped to a project (defaults
    to the currently-selected one)."""
    if project_id is None:
        project_id = get_current_project_id()
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        wb = writer.book

        # Formats — branded with TURF Landscape Co. colors
        header_fmt = wb.add_format({
            'bold': True, 'bg_color': BRAND_PRIMARY_COLOR, 'font_color': 'white',
            'border': 1, 'align': 'center', 'font_name': 'Arial', 'font_size': 11
        })
        cell_fmt = wb.add_format({'border': 1, 'align': 'center', 'font_name': 'Arial'})
        total_fmt = wb.add_format({
            'bold': True, 'bg_color': '#DCEFE8', 'border': 1,
            'align': 'center', 'font_name': 'Arial'
        })
        num_fmt = wb.add_format({'border': 1, 'align': 'center', 'num_format': '#,##0.00', 'font_name': 'Arial'})

        db = get_db()
        try:
            # Sheet 1: Employees
            employees = db.query(Employee).filter(Employee.project_id == project_id).all()
            emp_data = [{
                'كود': e.code, 'الاسم': e.name, 'المسمى الوظيفي': e.job_title or '',
                'القسم': e.department or '', 'الراتب': e.salary, 'المعدل اليومي': e.daily_rate,
                'الهاتف': e.phone or '', 'الرقم القومي': e.national_id or '',
                'المنطقة': e.area or '', 'تاريخ التعيين': str(e.hire_date or ''),
                'الحالة': e.status
            } for e in employees]
            emp_df = pd.DataFrame(emp_data)
            emp_df.to_excel(writer, sheet_name='الموظفون', index=False)
            _format_sheet(writer, 'الموظفون', emp_df, header_fmt, cell_fmt, wb)

            # Sheet 2: Attendance Records
            days_in_month = calendar.monthrange(year, month)[1]
            start_date = date(year, month, 1)
            end_date = date(year, month, days_in_month)
            att_records = db.query(Attendance).filter(
                Attendance.attendance_date >= start_date,
                Attendance.attendance_date <= end_date,
                Attendance.project_id == project_id,
            ).all()
            emp_dict = {e.id: e for e in employees}
            att_data = [{
                'كود الموظف': emp_dict[r.employee_id].code if r.employee_id in emp_dict else '',
                'اسم الموظف': emp_dict[r.employee_id].name if r.employee_id in emp_dict else '',
                'التاريخ': str(r.attendance_date),
                'الحالة': 'حاضر' if r.status == 1 else 'غائب',
                # Real headcount for this row (e.g. "5 عمال أشرف" -> 5), so a
                # later import (restore) can recover the actual matrix value
                # instead of collapsing every row back down to 1.
                'عدد الأفراد': r.workers_count if r.workers_count is not None else 1
            } for r in att_records]
            att_df = pd.DataFrame(att_data) if att_data else pd.DataFrame(columns=['كود الموظف', 'اسم الموظف', 'التاريخ', 'الحالة', 'عدد الأفراد'])
            att_df.to_excel(writer, sheet_name='سجلات الحضور', index=False)
            _format_sheet(writer, 'سجلات الحضور', att_df, header_fmt, cell_fmt, wb)

            # Sheet 3: Attendance Matrix
            matrix_df = get_attendance_matrix(month, year, project_id=project_id)
            if not matrix_df.empty:
                matrix_df.to_excel(writer, sheet_name='مصفوفة الحضور', index=False)
                ws = writer.sheets['مصفوفة الحضور']
                for col_num, col_name in enumerate(matrix_df.columns):
                    ws.write(0, col_num, col_name, header_fmt)
                    max_len = max(len(str(col_name)), matrix_df[col_name].astype(str).str.len().max() if len(matrix_df) > 0 else 5)
                    ws.set_column(col_num, col_num, min(max_len + 2, 20))
                for row_num, row in enumerate(matrix_df.itertuples(index=False), start=1):
                    for col_num, val in enumerate(row):
                        ws.write(row_num, col_num, val, cell_fmt)

            # Sheet 4: Overtime
            ot_records = db.query(Overtime).filter(
                Overtime.date >= start_date, Overtime.date <= end_date,
                Overtime.project_id == project_id,
            ).all()
            # Ignore exact historic duplicates in every report view. New
            # entries are prevented at save/import time; this protects old
            # data so a duplicate 2-hour entry is not shown as 4 hours.
            ot_records = unique_overtime_records(ot_records)
            ot_data = [{
                'كود الموظف': emp_dict[r.employee_id].code if r.employee_id in emp_dict else '',
                'اسم الموظف': emp_dict[r.employee_id].name if r.employee_id in emp_dict else '',
                'التاريخ': str(r.date), 'الساعات': r.hours,
                'معدل الساعة': r.rate_per_hour, 'الإجمالي': r.amount,
                'ملاحظات': r.notes or ''
            } for r in ot_records]
            ot_df = pd.DataFrame(ot_data) if ot_data else pd.DataFrame(columns=['كود الموظف', 'اسم الموظف', 'التاريخ', 'الساعات', 'معدل الساعة', 'الإجمالي', 'ملاحظات'])
            ot_df.to_excel(writer, sheet_name='الأوفر تايم', index=False)
            _format_sheet(writer, 'الأوفر تايم', ot_df, header_fmt, cell_fmt, wb)

            # Overtime matrix: the detailed sheet above is useful for audit,
            # while this monthly view mirrors the attendance matrix and makes
            # each employee's daily and total overtime immediately visible.
            overtime_matrix_df = get_overtime_matrix(month, year, project_id=project_id)
            if not overtime_matrix_df.empty:
                overtime_matrix_df.to_excel(writer, sheet_name='مصفوفة الأوفر تايم', index=False)
                ws = writer.sheets['مصفوفة الأوفر تايم']
                for col_num, col_name in enumerate(overtime_matrix_df.columns):
                    ws.write(0, col_num, col_name, header_fmt)
                    max_len = max(
                        len(str(col_name)),
                        overtime_matrix_df[col_name].astype(str).str.len().max()
                        if len(overtime_matrix_df) > 0 else 5,
                    )
                    ws.set_column(col_num, col_num, min(max_len + 2, 20))
                for row_num, row in enumerate(overtime_matrix_df.itertuples(index=False), start=1):
                    for col_num, value in enumerate(row):
                        ws.write(row_num, col_num, value, cell_fmt)

            # Sheet 5: Advances
            adv_records = db.query(Advance).filter(
                Advance.date >= start_date, Advance.date <= end_date,
                Advance.project_id == project_id,
            ).all()
            adv_data = [{
                'كود الموظف': emp_dict[r.employee_id].code if r.employee_id in emp_dict else '',
                'اسم الموظف': emp_dict[r.employee_id].name if r.employee_id in emp_dict else '',
                'التاريخ': str(r.date), 'المبلغ': r.amount, 'ملاحظات': r.notes or ''
            } for r in adv_records]
            adv_df = pd.DataFrame(adv_data) if adv_data else pd.DataFrame(columns=['كود الموظف', 'اسم الموظف', 'التاريخ', 'المبلغ', 'ملاحظات'])
            adv_df.to_excel(writer, sheet_name='السلف', index=False)
            _format_sheet(writer, 'السلف', adv_df, header_fmt, cell_fmt, wb)

            # Sheet 5b: Discounts
            disc_records = db.query(Discount).filter(
                Discount.date >= start_date, Discount.date <= end_date,
                Discount.project_id == project_id,
            ).all()
            disc_data = [{
                'كود الموظف': emp_dict[r.employee_id].code if r.employee_id in emp_dict else '',
                'اسم الموظف': emp_dict[r.employee_id].name if r.employee_id in emp_dict else '',
                'التاريخ': str(r.date),
                'نوع الخصم': DISCOUNT_TYPE_LABELS.get(r.discount_type, r.discount_type),
                'القيمة': r.amount, 'ملاحظات': r.notes or ''
            } for r in disc_records]
            disc_df = pd.DataFrame(disc_data) if disc_data else pd.DataFrame(
                columns=['كود الموظف', 'اسم الموظف', 'التاريخ', 'نوع الخصم', 'القيمة', 'ملاحظات']
            )
            disc_df.to_excel(writer, sheet_name='الخصومات', index=False)
            _format_sheet(writer, 'الخصومات', disc_df, header_fmt, cell_fmt, wb)

            # Sheet 6: Petty Cash (Expenses + Received Funds) — previously
            # missing from this report entirely (Phase 4A/4B fix): the
            # Expenses page had its own separate export, but the main
            # monthly report never included petty-cash data at all.
            exp_records = db.query(Expense).filter(
                Expense.date >= start_date, Expense.date <= end_date,
                Expense.project_id == project_id,
            ).all()
            fund_records = db.query(ReceivedFund).filter(
                ReceivedFund.date >= start_date, ReceivedFund.date <= end_date,
                ReceivedFund.project_id == project_id,
            ).all()
            petty_data = [{
                'النوع': 'مصروف', 'التاريخ': str(r.date), 'البيان / المصدر': r.description,
                'الفئة': r.category or '', 'المبلغ': r.amount, 'ملاحظات': r.notes or ''
            } for r in exp_records] + [{
                'النوع': 'وارد', 'التاريخ': str(r.date), 'البيان / المصدر': r.source or '',
                'الفئة': '', 'المبلغ': r.net_amount, 'ملاحظات': r.notes or ''
            } for r in fund_records]
            petty_df = pd.DataFrame(petty_data) if petty_data else pd.DataFrame(
                columns=['النوع', 'التاريخ', 'البيان / المصدر', 'الفئة', 'المبلغ', 'ملاحظات']
            )
            petty_df.to_excel(writer, sheet_name='النثريات', index=False)
            _format_sheet(writer, 'النثريات', petty_df, header_fmt, cell_fmt, wb)

            # Dated plant deliveries are included in the same monthly workbook.
            plant_records = db.query(
                PlantDelivery, PlantSupplier, PlantDeliveryLine, PlantItem
            ).join(
                PlantSupplier, PlantDelivery.supplier_id == PlantSupplier.id
            ).join(
                PlantDeliveryLine, PlantDeliveryLine.delivery_id == PlantDelivery.id
            ).join(
                PlantItem, PlantDeliveryLine.item_id == PlantItem.id
            ).filter(
                PlantDelivery.date >= start_date,
                PlantDelivery.date <= end_date,
                PlantDelivery.project_id == project_id,
            ).order_by(PlantDelivery.date, PlantDelivery.id, PlantDeliveryLine.id).all()
            plant_data = [{
                'التاريخ': str(delivery.date),
                'المورد': supplier.name,
                'الصنف': line.item_name_snapshot or item.name,
                'الكمية': line.quantity,
                'ملاحظات': delivery.notes or '',
                'رقم التوريد': delivery.id,
            } for delivery, supplier, line, item in plant_records]
            plant_df = pd.DataFrame(plant_data) if plant_data else pd.DataFrame(
                columns=['التاريخ', 'المورد', 'الصنف', 'الكمية', 'ملاحظات', 'رقم التوريد']
            )
            plant_df.to_excel(writer, sheet_name='توريدات الزرع', index=False)
            _format_sheet(writer, 'توريدات الزرع', plant_df, header_fmt, cell_fmt, wb)

            # Sheet 7: Payroll Summary
            payroll_df = calculate_payroll(month, year, project_id)
            if not payroll_df.empty:
                totals = {
                    'كود الموظف': '', 'اسم الموظف': 'الإجمالي', 'القسم': '',
                    'أيام الحضور': payroll_df['أيام الحضور'].sum(),
                    'المعدل اليومي': '',
                    'الراتب الأساسي': payroll_df['الراتب الأساسي'].sum(),
                    'الأوفر تايم': payroll_df['الأوفر تايم'].sum(),
                    'السلف': payroll_df['السلف'].sum(),
                    'الخصومات': payroll_df['الخصومات'].sum(),
                    'صافي الراتب': payroll_df['صافي الراتب'].sum()
                }
                totals_df = pd.DataFrame([totals])
                payroll_full = pd.concat([payroll_df, totals_df], ignore_index=True)
                payroll_full.to_excel(writer, sheet_name='مسير الرواتب', index=False)
                ws = writer.sheets['مسير الرواتب']
                for col_num, col_name in enumerate(payroll_full.columns):
                    ws.write(0, col_num, col_name, header_fmt)
                    ws.set_column(col_num, col_num, 18)
                for row_num, row in enumerate(payroll_full.itertuples(index=False), start=1):
                    fmt = total_fmt if row_num == len(payroll_full) else cell_fmt
                    for col_num, val in enumerate(row):
                        ws.write(row_num, col_num, val, fmt)
        finally:
            db.close()

    return output.getvalue()


def _sanitize_filename_part(name: str) -> str:
    """Make a project name safe to embed inside a filename.

    Strips characters that are invalid in Windows filenames
    (\\ / : * ? " < > |, plus control characters), collapses internal
    whitespace to single underscores, trims leading/trailing junk, and
    caps the length so an unusually long project name can't produce an
    unusable/too-long path. Arabic text passes through untouched
    otherwise, since it's valid in both Windows and POSIX filenames.
    """
    if not name:
        return ""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '', name)
    name = re.sub(r'\s+', '_', name.strip())
    name = name.strip('_.')
    return name[:60]


def build_export_filename(month: int, year: int, project_name: str = None) -> str:
    """Filename for a monthly export — always starts with 'TURF_HR' so a
    saved file is instantly recognizable in the Downloads folder among
    other apps' exports, and includes the project name (when known) so
    exports from different projects never look identical, e.g.
    'TURF_HR_Report_Downtown_Site_08_2026.xlsx'. Falls back to the
    project-less form ('TURF_HR_Report_08_2026.xlsx') if no project
    name is available."""
    project_part = _sanitize_filename_part(project_name)
    if project_part:
        return f"TURF_HR_Report_{project_part}_{int(month):02d}_{int(year)}.xlsx"
    return f"TURF_HR_Report_{int(month):02d}_{int(year)}.xlsx"


def save_full_report(month: int, year: int, project_id: int = None) -> tuple[bytes, str]:
    """
    Generate the full Excel report (see export_full_report above) AND
    physically write it to the user's real Downloads folder — never the
    process's current working directory and never the app's install
    folder (e.g. Program Files); see database.paths.get_downloads_dir.

    This is what fixes the "the report is generated but the file doesn't
    show up / isn't clearly saved" issue: relying only on the browser's
    download-button plumbing wasn't reliably producing a visible saved
    file when the app runs inside the desktop pywebview shell. Now a
    real file is always written to disk regardless of that, in both the
    plain-Python (streamlit run) and packaged .exe cases.

    The saved filename includes the exported project's name (see
    build_export_filename), so exporting several projects never
    produces indistinguishable files sitting side by side in Downloads.

    If a file with the same name already exists (e.g. re-exporting the
    same project + month twice), a " (2)", " (3)", ... suffix is
    appended instead of silently overwriting the previous export.

    Returns (data_bytes, saved_file_path).
    """
    if project_id is None:
        project_id = get_current_project_id()

    data = export_full_report(month, year, project_id)
    project_name = get_project_name(project_id)

    downloads_dir = get_downloads_dir()
    filename = build_export_filename(month, year, project_name)
    path = os.path.join(downloads_dir, filename)

    if os.path.exists(path):
        base, ext = os.path.splitext(filename)
        n = 2
        while os.path.exists(os.path.join(downloads_dir, f"{base} ({n}){ext}")):
            n += 1
        path = os.path.join(downloads_dir, f"{base} ({n}){ext}")

    with open(path, "wb") as f:
        f.write(data)

    return data, path


def _format_sheet(writer, sheet_name, df, header_fmt, cell_fmt, wb):
    if sheet_name not in writer.sheets:
        return
    ws = writer.sheets[sheet_name]
    for col_num, col_name in enumerate(df.columns):
        ws.write(0, col_num, col_name, header_fmt)
        max_len = max(len(str(col_name)), df[col_name].astype(str).str.len().max() if len(df) > 0 else 5)
        ws.set_column(col_num, col_num, min(max_len + 4, 30))
