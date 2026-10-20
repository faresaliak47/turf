"""
tests/test_excel.py — Excel export/import (Phase 4A Step 15).

Runs services.excel_export / services.excel_import directly with no
Streamlit involved (proving Step 9's "can be called from normal Python
code without Streamlit" for real, not just by inspection), using a
round-trip: export the current project's data to an in-memory .xlsx,
then import it into a second, empty project and check the data landed
correctly and stayed scoped to that second project.
"""
import io
import os
import unittest
from datetime import date
from tests import _bootstrap  # noqa: F401 — must be first
from tests.helpers import make_project, make_employee, reset_session_state, unique

from database.db import get_db
from database.models import Advance, Attendance, Discount, Employee, Expense, Overtime, ReceivedFund
from services.payroll_service import clear_payroll_cache
from services import excel_export, excel_import


def _add_attendance(employee_id: int, project_id: int, d: date):
    db = get_db()
    try:
        db.add(Attendance(employee_id=employee_id, attendance_date=d, status=1, project_id=project_id))
        db.commit()
    finally:
        db.close()


class TestExcelExportImportRoundTrip(unittest.TestCase):
    def setUp(self):
        reset_session_state()
        self.project = make_project()
        # Unique per test (not a fixed literal) so this class's tests
        # don't collide on Employee.code's global UNIQUE constraint when
        # run together against the shared temp test database.
        self.emp_code = unique("XLEMP")
        self.emp = make_employee(self.project.id, code=self.emp_code, name="Export Test", daily_rate=120)
        _add_attendance(self.emp.id, self.project.id, date(2026, 5, 1))

    def test_export_produces_readable_workbook(self):
        xlsx_bytes = excel_export.export_full_report(5, 2026, self.project.id)
        self.assertIsInstance(xlsx_bytes, (bytes, bytearray))
        self.assertGreater(len(xlsx_bytes), 0)

        is_valid, msg, sheets = excel_import.validate_file(xlsx_bytes)
        self.assertTrue(is_valid, msg)
        self.assertIn(excel_import.SHEET_EMPLOYEES, sheets)

        import pandas as pd
        workbook = pd.ExcelFile(io.BytesIO(xlsx_bytes))
        self.assertIn('مصفوفة الأوفر تايم', workbook.sheet_names)

    def test_import_into_second_project_is_scoped_correctly(self):
        xlsx_bytes = excel_export.export_full_report(5, 2026, self.project.id)
        is_valid, msg, sheets = excel_import.validate_file(xlsx_bytes)
        self.assertTrue(is_valid, msg)

        target_project = make_project()
        result = excel_import.import_report(sheets, mode='merge', project_id=target_project.id)
        self.assertIsInstance(result, dict)

        db = get_db()
        try:
            imported_emp = db.query(Employee).filter(
                Employee.code == self.emp_code, Employee.project_id == target_project.id,
            ).first()
            self.assertIsNotNone(imported_emp, "Imported employee not found scoped to target project")

            # The original project's employee must be untouched/unduplicated
            original_emp = db.query(Employee).filter(
                Employee.code == self.emp_code, Employee.project_id == self.project.id,
            ).first()
            self.assertIsNotNone(original_emp)
            self.assertNotEqual(imported_emp.id, original_emp.id)
        finally:
            db.close()

    def test_validate_file_rejects_garbage_bytes(self):
        is_valid, msg, sheets = excel_import.validate_file(b"not an excel file at all")
        self.assertFalse(is_valid)
        self.assertEqual(sheets, {})

    def test_export_includes_petty_cash_sheet_with_correct_data(self):
        db = get_db()
        try:
            db.add(Expense(date=date(2026, 5, 10), description="قرطاسية",
                            category="مكتب", amount=250, notes="", project_id=self.project.id))
            db.add(ReceivedFund(date=date(2026, 5, 12), amount=1000, tax=20,
                                 net_amount=980, source="تحويل بنكي", project_id=self.project.id))
            db.commit()
        finally:
            db.close()

        xlsx_bytes = excel_export.export_full_report(5, 2026, self.project.id)

        # 'النثريات' isn't one of excel_import's IMPORTABLE_SHEETS (it's
        # not meant to be re-imported), so read the workbook directly
        # rather than through validate_file() to confirm it's really there.
        import pandas as pd
        xl = pd.ExcelFile(io.BytesIO(xlsx_bytes))
        self.assertIn('النثريات', xl.sheet_names)

        petty_df = xl.parse('النثريات')
        self.assertEqual(len(petty_df), 2)
        amounts = set(petty_df['المبلغ'].tolist())
        self.assertIn(250, amounts)
        self.assertIn(980, amounts)

    def test_exact_duplicate_overtime_is_not_doubled_in_export(self):
        from database.models import Overtime
        db = get_db()
        try:
            # Simulates duplicate data created by an older version of the
            # bulk form. The export must show the employee's actual 2 hours.
            for _ in range(2):
                db.add(Overtime(
                    employee_id=self.emp.id, project_id=self.project.id,
                    date=date(2026, 5, 3), hours=2, rate_per_hour=15,
                    amount=30, notes='[BULK_OT] اختبار',
                ))
            db.commit()
        finally:
            db.close()

        xlsx_bytes = excel_export.export_full_report(5, 2026, self.project.id)
        import pandas as pd
        workbook = pd.ExcelFile(io.BytesIO(xlsx_bytes))
        detail = workbook.parse('الأوفر تايم')
        matrix = workbook.parse('مصفوفة الأوفر تايم')
        self.assertEqual(len(detail), 1)
        employee_row = matrix.loc[matrix['كود الموظف'] == self.emp_code].iloc[0]
        self.assertEqual(employee_row['3'], 2)
        self.assertEqual(employee_row['إجمالي الأوفر تايم'], 2)


class TestSaveFullReportToDownloads(unittest.TestCase):
    """services.excel_export.save_full_report() — the fix for 'the
    report is generated but the file doesn't show up / isn't clearly
    saved'. Must write a real file to disk, name it starting with
    'TURF_HR', and never write into the current working directory."""

    def setUp(self):
        reset_session_state()
        self.project = make_project()
        self.emp = make_employee(self.project.id, code=unique("XLSAVE"), name="Save Test", daily_rate=100)

    def test_save_full_report_writes_real_file_with_turf_hr_name(self):
        cwd_before = os.getcwd()
        data, saved_path = excel_export.save_full_report(6, 2026, self.project.id)

        self.assertIsInstance(data, (bytes, bytearray))
        self.assertGreater(len(data), 0)

        self.assertTrue(os.path.exists(saved_path), f"File was not actually written: {saved_path}")
        filename = os.path.basename(saved_path)
        self.assertTrue(filename.startswith("TURF_HR_Report_"), filename)
        self.assertTrue(filename.endswith("_06_2026.xlsx"), filename)
        # Project name is embedded in the filename.
        expected_project_part = excel_export._sanitize_filename_part(self.project.name)
        self.assertIn(expected_project_part, filename)

        # Never saved into the process's current working directory.
        self.assertNotEqual(os.path.dirname(os.path.abspath(saved_path)), os.path.abspath(cwd_before))

        with open(saved_path, "rb") as f:
            on_disk = f.read()
        self.assertEqual(on_disk, data)

        os.remove(saved_path)

    def test_save_full_report_does_not_overwrite_existing_export(self):
        _data1, path1 = excel_export.save_full_report(7, 2026, self.project.id)
        _data2, path2 = excel_export.save_full_report(7, 2026, self.project.id)
        try:
            self.assertNotEqual(path1, path2)
            self.assertTrue(os.path.exists(path1))
            self.assertTrue(os.path.exists(path2))
        finally:
            for p in (path1, path2):
                if os.path.exists(p):
                    os.remove(p)

    def test_build_export_filename_format(self):
        self.assertEqual(
            excel_export.build_export_filename(8, 2026, "Downtown Site"),
            "TURF_HR_Report_Downtown_Site_08_2026.xlsx",
        )
        self.assertEqual(
            excel_export.build_export_filename(1, 2026, "Downtown Site"),
            "TURF_HR_Report_Downtown_Site_01_2026.xlsx",
        )
        # No project name available -> falls back to the project-less form.
        self.assertEqual(
            excel_export.build_export_filename(8, 2026, None),
            "TURF_HR_Report_08_2026.xlsx",
        )

    def test_build_export_filename_sanitizes_invalid_characters(self):
        unsafe = 'Site: A/B\\C*?"<>|'
        filename = excel_export.build_export_filename(8, 2026, unsafe)
        self.assertTrue(filename.startswith("TURF_HR_Report_"))
        self.assertTrue(filename.endswith("_08_2026.xlsx"))
        for bad_char in '\\/:*?"<>|':
            self.assertNotIn(bad_char, filename)


class TestFullReportReconciliation(unittest.TestCase):
    """End-to-end audit: every report sheet must match source data exactly."""
    def setUp(self):
        reset_session_state()
        clear_payroll_cache()
        self.project = make_project()
        self.other_project = make_project()
        self.emp_a = make_employee(
            self.project.id, code=unique('REPA'), name='Report A', daily_rate=100,
        )
        self.emp_b = make_employee(
            self.project.id, code=unique('REPB'), name='Report B', daily_rate=120,
        )
        self.other_emp = make_employee(
            self.other_project.id, code=unique('REPX'), name='Other Project', daily_rate=999,
        )
        self.month, self.year = 5, 2026

        db = get_db()
        try:
            # Project being exported: attendance, overtime, advance,
            # discount, and petty cash all have deliberately different totals.
            db.add_all([
                Attendance(employee_id=self.emp_a.id, project_id=self.project.id,
                           attendance_date=date(2026, 5, 1), status=1, workers_count=1),
                Attendance(employee_id=self.emp_a.id, project_id=self.project.id,
                           attendance_date=date(2026, 5, 2), status=1, workers_count=1),
                Attendance(employee_id=self.emp_a.id, project_id=self.project.id,
                           attendance_date=date(2026, 5, 3), status=0, workers_count=1),
                Attendance(employee_id=self.emp_b.id, project_id=self.project.id,
                           attendance_date=date(2026, 5, 1), status=1, workers_count=1),
                Overtime(employee_id=self.emp_a.id, project_id=self.project.id,
                         date=date(2026, 5, 2), hours=2, rate_per_hour=15, amount=30, notes='عمل ليلي'),
                Advance(employee_id=self.emp_a.id, project_id=self.project.id,
                        date=date(2026, 5, 4), amount=20, notes='سلفة'),
                Discount(employee_id=self.emp_a.id, project_id=self.project.id,
                         date=date(2026, 5, 5), discount_type='amount', amount=10,
                         hours=0, rate_snapshot=0, notes='تأخير'),
                Expense(project_id=self.project.id, date=date(2026, 5, 6),
                        description='وقود', category='تشغيل', amount=70, notes=''),
                ReceivedFund(project_id=self.project.id, date=date(2026, 5, 7),
                             amount=100, tax=5, net_amount=95, source='تحويل', notes=''),
                # Data in another project must never leak into this workbook.
                Attendance(employee_id=self.other_emp.id, project_id=self.other_project.id,
                           attendance_date=date(2026, 5, 1), status=1, workers_count=1),
                Overtime(employee_id=self.other_emp.id, project_id=self.other_project.id,
                         date=date(2026, 5, 1), hours=9, rate_per_hour=99, amount=891, notes='لا يظهر'),
                Advance(employee_id=self.other_emp.id, project_id=self.other_project.id,
                        date=date(2026, 5, 1), amount=777, notes='لا يظهر'),
                Discount(employee_id=self.other_emp.id, project_id=self.other_project.id,
                         date=date(2026, 5, 1), discount_type='amount', amount=666,
                         hours=0, rate_snapshot=0, notes='لا يظهر'),
                Expense(project_id=self.other_project.id, date=date(2026, 5, 1),
                        description='لا يظهر', category='أخرى', amount=555, notes=''),
            ])
            db.commit()
        finally:
            db.close()

    def test_every_sheet_matches_source_data_and_excludes_other_projects(self):
        report = excel_export.export_full_report(self.month, self.year, self.project.id)
        import pandas as pd
        workbook = pd.ExcelFile(io.BytesIO(report))

        expected_sheets = {
            'الموظفون', 'سجلات الحضور', 'مصفوفة الحضور', 'الأوفر تايم',
            'مصفوفة الأوفر تايم', 'السلف', 'الخصومات', 'النثريات', 'مسير الرواتب',
        }
        self.assertTrue(expected_sheets.issubset(set(workbook.sheet_names)))

        employees = workbook.parse('الموظفون')
        self.assertEqual(set(employees['كود']), {self.emp_a.code, self.emp_b.code})

        attendance = workbook.parse('سجلات الحضور')
        self.assertEqual(len(attendance), 4)  # includes one recorded absence
        attendance_matrix = workbook.parse('مصفوفة الحضور')
        row_a_att = attendance_matrix.loc[attendance_matrix['كود الموظف'] == self.emp_a.code].iloc[0]
        self.assertEqual(row_a_att['إجمالي الحضور'], 2)

        overtime = workbook.parse('الأوفر تايم')
        self.assertEqual(len(overtime), 1)
        self.assertEqual(overtime.iloc[0]['الساعات'], 2)
        self.assertEqual(overtime.iloc[0]['الإجمالي'], 30)
        overtime_matrix = workbook.parse('مصفوفة الأوفر تايم')
        row_a_ot = overtime_matrix.loc[overtime_matrix['كود الموظف'] == self.emp_a.code].iloc[0]
        self.assertEqual(row_a_ot['2'], 2)
        self.assertEqual(row_a_ot['إجمالي الأوفر تايم'], 2)

        advances = workbook.parse('السلف')
        discounts = workbook.parse('الخصومات')
        self.assertEqual(advances['المبلغ'].sum(), 20)
        self.assertEqual(discounts['القيمة'].sum(), 10)

        petty_cash = workbook.parse('النثريات')
        self.assertEqual(set(petty_cash['المبلغ']), {70, 95})

        payroll = workbook.parse('مسير الرواتب')
        row_a_payroll = payroll.loc[payroll['كود الموظف'] == self.emp_a.code].iloc[0]
        self.assertEqual(row_a_payroll['أيام الحضور'], 2)
        self.assertEqual(row_a_payroll['الراتب الأساسي'], 200)
        self.assertEqual(row_a_payroll['الأوفر تايم'], 30)
        self.assertEqual(row_a_payroll['السلف'], 20)
        self.assertEqual(row_a_payroll['الخصومات'], 10)
        self.assertEqual(row_a_payroll['صافي الراتب'], 200)
        self.assertNotIn(self.other_emp.code, set(payroll['كود الموظف'].dropna()))


if __name__ == "__main__":
    unittest.main()
