"""
tests/test_projects_delete.py — Delete Project feature.
"""
import unittest
from datetime import date
from tests import _bootstrap  # noqa: F401 — must be first
from tests.helpers import make_project, make_employee, reset_session_state

from database.db import get_db
from database.models import Project, Employee, Expense, ReceivedFund, Attendance, Overtime, Advance
from services import projects as projects_service


class TestDeleteProject(unittest.TestCase):
    def setUp(self):
        reset_session_state()

    def test_delete_empty_project_succeeds(self):
        # Make sure there are at least two projects so this isn't "the
        # last one" from the guard's point of view.
        make_project()
        empty_project = make_project()

        ok, msg = projects_service.delete_project(empty_project.id)
        self.assertTrue(ok, msg)

        db = get_db()
        try:
            self.assertIsNone(db.query(Project).filter(Project.id == empty_project.id).first())
        finally:
            db.close()

    def test_delete_cascades_employees_and_their_related_records(self):
        make_project()
        project = make_project()
        emp = make_employee(project.id, code="DP001", name="Test Employee")
        db = get_db()
        try:
            db.add(Attendance(employee_id=emp.id, attendance_date=date.today(), status=1, project_id=project.id))
            db.add(Overtime(employee_id=emp.id, date=date.today(), hours=2, rate_per_hour=10, amount=20, project_id=project.id))
            db.add(Advance(employee_id=emp.id, date=date.today(), amount=50, project_id=project.id))
            db.commit()
        finally:
            db.close()

        ok, msg = projects_service.delete_project(project.id)
        self.assertTrue(ok, msg)
        self.assertIn("موظف", msg)

        db = get_db()
        try:
            self.assertIsNone(db.query(Project).filter(Project.id == project.id).first())
            self.assertIsNone(db.query(Employee).filter(Employee.id == emp.id).first())
            self.assertEqual(db.query(Attendance).filter(Attendance.employee_id == emp.id).count(), 0)
            self.assertEqual(db.query(Overtime).filter(Overtime.employee_id == emp.id).count(), 0)
            self.assertEqual(db.query(Advance).filter(Advance.employee_id == emp.id).count(), 0)
        finally:
            db.close()

    def test_delete_cascades_expenses_linked(self):
        make_project()
        project = make_project()
        db = get_db()
        try:
            exp = Expense(date=date.today(), description="test", amount=10, project_id=project.id)
            db.add(exp)
            db.commit()
            exp_id = exp.id
        finally:
            db.close()

        ok, msg = projects_service.delete_project(project.id)
        self.assertTrue(ok, msg)

        db = get_db()
        try:
            self.assertIsNone(db.query(Project).filter(Project.id == project.id).first())
            self.assertIsNone(db.query(Expense).filter(Expense.id == exp_id).first())
        finally:
            db.close()

    def test_delete_cascades_received_funds_linked(self):
        make_project()
        project = make_project()
        db = get_db()
        try:
            fund = ReceivedFund(date=date.today(), amount=100, net_amount=100, project_id=project.id)
            db.add(fund)
            db.commit()
            fund_id = fund.id
        finally:
            db.close()

        ok, msg = projects_service.delete_project(project.id)
        self.assertTrue(ok, msg)

        db = get_db()
        try:
            self.assertIsNone(db.query(Project).filter(Project.id == project.id).first())
            self.assertIsNone(db.query(ReceivedFund).filter(ReceivedFund.id == fund_id).first())
        finally:
            db.close()

    def test_delete_refused_for_last_remaining_project(self):
        db = get_db()
        try:
            # Delete every project so only one remains, deterministically.
            all_ids = [p.id for p in db.query(Project).all()]
        finally:
            db.close()
        # Keep exactly one project around for this test.
        only_project = make_project()
        for pid in all_ids:
            projects_service.delete_project(pid)  # best-effort cleanup; may be refused, that's fine

        remaining = projects_service.list_projects()
        if len(remaining) == 1:
            ok, msg = projects_service.delete_project(remaining[0].id)
            self.assertFalse(ok)
            self.assertIn("الوحيد", msg)

    def test_delete_does_not_affect_other_projects(self):
        project_a = make_project()
        project_b = make_project()
        make_employee(project_a.id, code="DP010", name="Employee A")

        ok, msg = projects_service.delete_project(project_b.id)
        self.assertTrue(ok, msg)

        db = get_db()
        try:
            self.assertIsNotNone(db.query(Project).filter(Project.id == project_a.id).first())
        finally:
            db.close()

    def test_delete_nonexistent_project(self):
        ok, msg = projects_service.delete_project(999999)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
