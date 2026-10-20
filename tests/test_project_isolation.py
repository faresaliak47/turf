"""
tests/test_project_isolation.py — Cross-cutting project isolation suite
(Phase 4A Step 15's explicitly named "Project isolation" test group).

Per-service isolation tests already live alongside each CRUD test module
(TestEmployeeProjectIsolation in test_employees.py, etc.) so each bug fix
is tested right next to its own code. This module is the single place
that states the rule once, across every scoped table, as a quick
end-to-end checklist — useful as a fast "did we break isolation
somewhere" smoke test after future changes.
"""
import unittest
from datetime import date
from tests import _bootstrap  # noqa: F401 — must be first
from tests.helpers import make_project, make_employee, reset_session_state

from services import employee_service, overtime_service, advance_service, attendance_service


class TestCrossServiceProjectIsolation(unittest.TestCase):
    def setUp(self):
        reset_session_state()
        self.project_a = make_project()
        self.project_b = make_project()
        self.emp_a = make_employee(self.project_a.id)
        self.emp_b = make_employee(self.project_b.id)

    def test_employees_isolated(self):
        ids_a = {e.id for e in employee_service.list_employees(self.project_a.id)}
        ids_b = {e.id for e in employee_service.list_employees(self.project_b.id)}
        self.assertTrue(ids_a.isdisjoint(ids_b))
        self.assertIn(self.emp_a.id, ids_a)
        self.assertIn(self.emp_b.id, ids_b)

    def test_overtime_isolated(self):
        overtime_service.create_overtime(
            project_id=self.project_b.id, employee_id=self.emp_b.id,
            ot_date=date.today(), hours=1, rate_per_hour=10, amount=10,
        )
        rec = overtime_service.find_duplicate(self.emp_b.id, date.today())
        # Project A must not be able to touch it
        ok_update, _ = overtime_service.update_overtime(
            record_id=rec.id, project_id=self.project_a.id, employee_id=self.emp_b.id,
            ot_date=date.today(), hours=99, rate_per_hour=10, amount=990,
        )
        ok_delete, _ = overtime_service.delete_overtime(rec.id, self.project_a.id)
        self.assertFalse(ok_update)
        self.assertFalse(ok_delete)

    def test_advances_isolated(self):
        advance_service.create_advance(
            project_id=self.project_b.id, employee_id=self.emp_b.id,
            adv_date=date.today(), amount=50,
        )
        from database.db import get_db
        from database.models import Advance
        db = get_db()
        try:
            rec_id = db.query(Advance).filter(Advance.employee_id == self.emp_b.id).first().id
        finally:
            db.close()

        ok_update, _ = advance_service.update_advance(
            record_id=rec_id, project_id=self.project_a.id, employee_id=self.emp_b.id,
            adv_date=date.today(), amount=1,
        )
        ok_delete, _ = advance_service.delete_advance(rec_id, self.project_a.id)
        self.assertFalse(ok_update)
        self.assertFalse(ok_delete)

    def test_attendance_isolated(self):
        """attendance_service was already correctly scoped before Phase
        4A (see audit) — included here so the cross-cutting checklist
        covers every operational table, not just the three that needed
        fixing."""
        from database.db import get_db
        from database.models import Attendance
        db = get_db()
        try:
            db.add(Attendance(
                employee_id=self.emp_b.id, attendance_date=date.today(),
                status=1, project_id=self.project_b.id,
            ))
            db.commit()
            rec_id = db.query(Attendance).filter(Attendance.employee_id == self.emp_b.id).first().id
        finally:
            db.close()

        ok_update, _ = attendance_service.update_attendance_record(
            record_id=rec_id, project_id=self.project_a.id, employee_id=self.emp_b.id,
            attendance_date=date.today(),
        )
        ok_delete, _ = attendance_service.delete_attendance_record(rec_id, self.project_a.id)
        self.assertFalse(ok_update)
        self.assertFalse(ok_delete)


if __name__ == "__main__":
    unittest.main()
