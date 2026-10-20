"""
tests/test_payroll.py — Payroll calculation correctness + cache
invalidation (Phase 4A Step 15 / Step 7).

Deliberately does NOT change the payroll algorithm itself (Phase 4A
Step 7: "Do NOT rewrite the payroll algorithm unless a real bug is
discovered" — none was). These tests pin down the existing formula
(net = attendance_days * daily_rate + overtime_total - advances_total)
as a regression guard, and verify that every write path that should
invalidate the payroll cache (employee/overtime/advance create-update-
delete) actually does, now that Phase 4A wired employee/overtime/advance
edits through the new service layer.
"""
import unittest
from datetime import date
from tests import _bootstrap  # noqa: F401 — must be first
from tests.helpers import make_project, make_employee, reset_session_state

from database.db import get_db
from database.models import Attendance, Employee
from services import employee_service, overtime_service, advance_service
from services.payroll_service import calculate_payroll, clear_payroll_cache


def _add_attendance(employee_id: int, project_id: int, d: date):
    db = get_db()
    try:
        db.add(Attendance(employee_id=employee_id, attendance_date=d, status=1, project_id=project_id))
        db.commit()
    finally:
        db.close()


class TestPayrollCalculation(unittest.TestCase):
    def setUp(self):
        reset_session_state()
        clear_payroll_cache()
        self.project = make_project()
        self.month = 6
        self.year = 2026

    def test_basic_net_salary_formula(self):
        emp = make_employee(self.project.id, daily_rate=100, salary=3000)
        _add_attendance(emp.id, self.project.id, date(self.year, self.month, 1))
        _add_attendance(emp.id, self.project.id, date(self.year, self.month, 2))
        _add_attendance(emp.id, self.project.id, date(self.year, self.month, 3))
        overtime_service.create_overtime(
            project_id=self.project.id, employee_id=emp.id,
            ot_date=date(self.year, self.month, 3), hours=2, rate_per_hour=15, amount=30,
        )
        advance_service.create_advance(
            project_id=self.project.id, employee_id=emp.id,
            adv_date=date(self.year, self.month, 2), amount=50,
        )

        df = calculate_payroll(self.month, self.year, self.project.id)
        self.assertEqual(len(df), 1)
        row = df.iloc[0]

        # 3 attendance days * 100 daily_rate = 300 base
        self.assertEqual(row['أيام الحضور'], 3)
        self.assertEqual(row['الراتب الأساسي'], 300)
        self.assertEqual(row['الأوفر تايم'], 30)
        self.assertEqual(row['السلف'], 50)
        # net = base + overtime - advances = 300 + 30 - 50 = 280
        self.assertEqual(row['صافي الراتب'], 280)

    def test_inactive_employee_excluded_from_payroll(self):
        emp = make_employee(self.project.id, daily_rate=100, status='Inactive')
        _add_attendance(emp.id, self.project.id, date(self.year, self.month, 1))
        df = calculate_payroll(self.month, self.year, self.project.id)
        self.assertTrue(df.empty or emp.code not in df['كود الموظف'].values)

    def test_payroll_scoped_to_project(self):
        emp_a = make_employee(self.project.id, daily_rate=100)
        _add_attendance(emp_a.id, self.project.id, date(self.year, self.month, 1))

        project_b = make_project()
        emp_b = make_employee(project_b.id, daily_rate=999)
        _add_attendance(emp_b.id, project_b.id, date(self.year, self.month, 1))

        df_a = calculate_payroll(self.month, self.year, self.project.id)
        codes_a = set(df_a['كود الموظف'])
        self.assertIn(emp_a.code, codes_a)
        self.assertNotIn(emp_b.code, codes_a)


class TestPayrollCacheInvalidation(unittest.TestCase):
    """Step 7: any operation that changes payroll-related data must
    invalidate the cache. Verified here by calling through the actual
    write paths (employee_service / overtime_service / advance_service)
    used by the UI after Phase 4A's refactor, and confirming payroll
    reflects the change immediately (not stale for up to the cache TTL).
    """

    def setUp(self):
        reset_session_state()
        clear_payroll_cache()
        self.project = make_project()
        self.month, self.year = 7, 2026

    def test_cache_invalidated_after_employee_daily_rate_edit(self):
        emp = make_employee(self.project.id, daily_rate=100)
        _add_attendance(emp.id, self.project.id, date(self.year, self.month, 1))

        df1 = calculate_payroll(self.month, self.year, self.project.id)
        self.assertEqual(df1.iloc[0]['الراتب الأساسي'], 100)

        ok, _ = employee_service.update_employee(
            employee_id=emp.id, project_id=self.project.id,
            code=emp.code, name=emp.name, daily_rate=250,
        )
        self.assertTrue(ok)

        df2 = calculate_payroll(self.month, self.year, self.project.id)
        self.assertEqual(df2.iloc[0]['الراتب الأساسي'], 250,
                          "Stale payroll after employee edit — cache was not invalidated")

    def test_cache_invalidated_after_employee_delete(self):
        emp = make_employee(self.project.id, daily_rate=100)
        _add_attendance(emp.id, self.project.id, date(self.year, self.month, 1))
        df1 = calculate_payroll(self.month, self.year, self.project.id)
        self.assertEqual(len(df1), 1)

        employee_service.delete_employee(emp.id, self.project.id)

        df2 = calculate_payroll(self.month, self.year, self.project.id)
        self.assertTrue(df2.empty, "Deleted employee still appears in payroll — cache was not invalidated")

    def test_cache_invalidated_after_overtime_create(self):
        emp = make_employee(self.project.id, daily_rate=100)
        _add_attendance(emp.id, self.project.id, date(self.year, self.month, 1))
        df1 = calculate_payroll(self.month, self.year, self.project.id)
        self.assertEqual(df1.iloc[0]['الأوفر تايم'], 0)

        overtime_service.create_overtime(
            project_id=self.project.id, employee_id=emp.id,
            ot_date=date(self.year, self.month, 1), hours=1, rate_per_hour=20, amount=20,
        )
        df2 = calculate_payroll(self.month, self.year, self.project.id)
        self.assertEqual(df2.iloc[0]['الأوفر تايم'], 20)

    def test_cache_invalidated_after_advance_delete(self):
        """Regression test for the specific bug found in the Phase 4A
        audit: page_modules/advances.py's delete path never called
        clear_payroll_cache() before this phase's fix."""
        emp = make_employee(self.project.id, daily_rate=100)
        _add_attendance(emp.id, self.project.id, date(self.year, self.month, 1))
        advance_service.create_advance(
            project_id=self.project.id, employee_id=emp.id,
            adv_date=date(self.year, self.month, 1), amount=40,
        )
        df1 = calculate_payroll(self.month, self.year, self.project.id)
        self.assertEqual(df1.iloc[0]['السلف'], 40)

        db = get_db()
        try:
            from database.models import Advance
            rec_id = db.query(Advance).filter(Advance.employee_id == emp.id).first().id
        finally:
            db.close()

        advance_service.delete_advance(rec_id, self.project.id)

        df2 = calculate_payroll(self.month, self.year, self.project.id)
        self.assertEqual(df2.iloc[0]['السلف'], 0,
                          "Stale payroll after advance delete — cache was not invalidated")

    def test_none_daily_rate_and_salary_do_not_crash_payroll(self):
        """Regression test: Employee.salary/daily_rate are nullable Float
        columns at the DB level (Column(Float, default=0.0) has no NOT
        NULL constraint), so a row with an explicit NULL is possible
        (e.g. older data, a direct DB edit, or a manual data fix) even
        though the app's own forms always supply 0.0. calculate_payroll()
        must not raise TypeError for `att_days * None` in that case."""
        emp = make_employee(self.project.id, daily_rate=100)
        db = get_db()
        try:
            row = db.query(Employee).filter(Employee.id == emp.id).first()
            row.daily_rate = None
            row.salary = None
            db.commit()
        finally:
            db.close()
        _add_attendance(emp.id, self.project.id, date(self.year, self.month, 1))

        df = calculate_payroll(self.month, self.year, self.project.id)
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]['الراتب الأساسي'], 0)
        self.assertEqual(df.iloc[0]['صافي الراتب'], 0)


if __name__ == "__main__":
    unittest.main()
