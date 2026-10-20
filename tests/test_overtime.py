"""
tests/test_overtime.py — Overtime CRUD + project isolation (Phase 4A
Step 15). Covers services.overtime_service (Phase 4A fix for the
audit-found project-scope gap — see its module docstring).
"""
import unittest
from datetime import date
from tests import _bootstrap  # noqa: F401 — must be first
from tests.helpers import make_project, make_employee, reset_session_state, today

from database.db import get_db
from database.models import Overtime
from services import overtime_service


class TestOvertimeCRUD(unittest.TestCase):
    def setUp(self):
        reset_session_state()
        self.project = make_project()
        self.emp = make_employee(self.project.id)

    def test_create_overtime(self):
        ok, msg = overtime_service.create_overtime(
            project_id=self.project.id, employee_id=self.emp.id,
            ot_date=today(), hours=2, rate_per_hour=10, amount=20,
        )
        self.assertTrue(ok, msg)
        db = get_db()
        try:
            rec = db.query(Overtime).filter(Overtime.employee_id == self.emp.id).first()
            self.assertIsNotNone(rec)
            self.assertEqual(rec.amount, 20)
        finally:
            db.close()

    def test_find_duplicate(self):
        overtime_service.create_overtime(
            project_id=self.project.id, employee_id=self.emp.id,
            ot_date=today(), hours=2, rate_per_hour=10, amount=20,
        )
        dup = overtime_service.find_duplicate(self.emp.id, today())
        self.assertIsNotNone(dup)

        no_dup = overtime_service.find_duplicate(self.emp.id, today(), exclude_id=dup.id)
        self.assertIsNone(no_dup)

    def test_update_overtime(self):
        ok, _ = overtime_service.create_overtime(
            project_id=self.project.id, employee_id=self.emp.id,
            ot_date=today(), hours=2, rate_per_hour=10, amount=20,
        )
        rec = overtime_service.find_duplicate(self.emp.id, today())

        ok, msg = overtime_service.update_overtime(
            record_id=rec.id, project_id=self.project.id, employee_id=self.emp.id,
            ot_date=today(), hours=5, rate_per_hour=10, amount=50,
        )
        self.assertTrue(ok, msg)

        db = get_db()
        try:
            refreshed = db.query(Overtime).filter(Overtime.id == rec.id).first()
            self.assertEqual(refreshed.amount, 50)
        finally:
            db.close()

    def test_update_overtime_blocks_duplicate_date(self):
        """Editing one overtime record to collide with ANOTHER existing
        record for the same employee+date must be rejected."""
        emp2_date_record = overtime_service.create_overtime(
            project_id=self.project.id, employee_id=self.emp.id,
            ot_date=today(), hours=1, rate_per_hour=10, amount=10,
        )
        other_emp = make_employee(self.project.id)
        overtime_service.create_overtime(
            project_id=self.project.id, employee_id=other_emp.id,
            ot_date=today(), hours=1, rate_per_hour=10, amount=10,
        )
        rec_for_other = overtime_service.find_duplicate(other_emp.id, today())

        # Try to edit other_emp's record to point at self.emp's date —
        # collides with self.emp's existing record.
        ok, msg = overtime_service.update_overtime(
            record_id=rec_for_other.id, project_id=self.project.id,
            employee_id=self.emp.id, ot_date=today(), hours=1,
            rate_per_hour=10, amount=10,
        )
        self.assertFalse(ok)

    def test_delete_overtime(self):
        overtime_service.create_overtime(
            project_id=self.project.id, employee_id=self.emp.id,
            ot_date=today(), hours=2, rate_per_hour=10, amount=20,
        )
        rec = overtime_service.find_duplicate(self.emp.id, today())
        ok, msg = overtime_service.delete_overtime(rec.id, self.project.id)
        self.assertTrue(ok, msg)

        db = get_db()
        try:
            self.assertIsNone(db.query(Overtime).filter(Overtime.id == rec.id).first())
        finally:
            db.close()

    def test_monthly_matrix_sums_hours_per_day_and_total(self):
        """The matrix must aggregate multiple same-day rows, not discard one."""
        overtime_service.create_overtime(
            project_id=self.project.id, employee_id=self.emp.id,
            ot_date=date(2026, 5, 3), hours=2, rate_per_hour=10, amount=20,
        )
        overtime_service.create_overtime(
            project_id=self.project.id, employee_id=self.emp.id,
            ot_date=date(2026, 5, 3), hours=1.5, rate_per_hour=10, amount=15,
        )
        matrix = overtime_service.get_overtime_matrix(5, 2026, project_id=self.project.id)
        row = matrix.loc[matrix['كود الموظف'] == self.emp.code].iloc[0]
        self.assertEqual(row['3'], 3.5)
        self.assertEqual(row['إجمالي الأوفر تايم'], 3.5)

    def test_exact_duplicate_is_not_saved_twice(self):
        args = dict(
            project_id=self.project.id, employee_id=self.emp.id,
            ot_date=date(2026, 5, 4), hours=2, rate_per_hour=10, amount=20,
            notes='اختبار',
        )
        self.assertTrue(overtime_service.create_overtime(**args)[0])
        ok, message = overtime_service.create_overtime(**args)
        self.assertFalse(ok)
        self.assertIn('مطابق', message)


class TestOvertimeProjectIsolation(unittest.TestCase):
    def setUp(self):
        reset_session_state()
        self.project_a = make_project()
        self.project_b = make_project()
        self.emp_b = make_employee(self.project_b.id)
        overtime_service.create_overtime(
            project_id=self.project_b.id, employee_id=self.emp_b.id,
            ot_date=today(), hours=3, rate_per_hour=10, amount=30,
        )
        self.rec_b = overtime_service.find_duplicate(self.emp_b.id, today())

    def test_project_a_cannot_update_project_b_overtime(self):
        ok, msg = overtime_service.update_overtime(
            record_id=self.rec_b.id, project_id=self.project_a.id,
            employee_id=self.emp_b.id, ot_date=today(), hours=99,
            rate_per_hour=10, amount=990,
        )
        self.assertFalse(ok)
        db = get_db()
        try:
            still = db.query(Overtime).filter(Overtime.id == self.rec_b.id).first()
            self.assertEqual(still.amount, 30)
        finally:
            db.close()

    def test_project_a_cannot_delete_project_b_overtime(self):
        ok, msg = overtime_service.delete_overtime(self.rec_b.id, self.project_a.id)
        self.assertFalse(ok)
        db = get_db()
        try:
            self.assertIsNotNone(db.query(Overtime).filter(Overtime.id == self.rec_b.id).first())
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
