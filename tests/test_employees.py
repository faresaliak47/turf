"""
tests/test_employees.py — Employee CRUD + project isolation (Phase 4A
Step 15).

Covers services.employee_service, the module created in Phase 4A to fix
two audit-found bugs: missing project-scope enforcement at the query
level, and missing payroll-cache invalidation on edit/delete (see
services/employee_service.py's module docstring for details).
"""
import unittest
from tests import _bootstrap  # noqa: F401 — must be first
from tests.helpers import make_project, make_employee, reset_session_state, unique

from database.db import get_db
from database.models import Employee
from services import employee_service


class TestEmployeeCRUD(unittest.TestCase):
    def setUp(self):
        reset_session_state()
        self.project = make_project()

    def test_create_employee(self):
        ok, msg = employee_service.create_employee(
            project_id=self.project.id, code="EMP001", name="Ahmed Test",
            salary=3000, daily_rate=100,
        )
        self.assertTrue(ok, msg)

        db = get_db()
        try:
            emp = db.query(Employee).filter(Employee.code == "EMP001").first()
            self.assertIsNotNone(emp)
            self.assertEqual(emp.name, "Ahmed Test")
            self.assertEqual(emp.project_id, self.project.id)
        finally:
            db.close()

    def test_create_duplicate_code_rejected(self):
        ok1, _ = employee_service.create_employee(
            project_id=self.project.id, code="DUPCODE", name="First",
        )
        self.assertTrue(ok1)
        ok2, msg2 = employee_service.create_employee(
            project_id=self.project.id, code="DUPCODE", name="Second",
        )
        self.assertFalse(ok2)
        self.assertIn("مستخدم", msg2)

    def test_create_missing_required_fields_rejected(self):
        ok, msg = employee_service.create_employee(project_id=self.project.id, code="", name="")
        self.assertFalse(ok)

    def test_read_list_employees_scoped_to_project(self):
        make_employee(self.project.id)
        make_employee(self.project.id)
        other_project = make_project()
        make_employee(other_project.id)

        emps = employee_service.list_employees(self.project.id)
        self.assertEqual(len(emps), 2)
        for e in emps:
            self.assertEqual(e.project_id, self.project.id)

    def test_update_employee(self):
        emp = make_employee(self.project.id, name="Old Name", salary=1000)
        ok, msg = employee_service.update_employee(
            employee_id=emp.id, project_id=self.project.id,
            code=emp.code, name="New Name", salary=5000, daily_rate=200,
        )
        self.assertTrue(ok, msg)

        db = get_db()
        try:
            refreshed = db.query(Employee).filter(Employee.id == emp.id).first()
            self.assertEqual(refreshed.name, "New Name")
            self.assertEqual(refreshed.salary, 5000)
        finally:
            db.close()

    def test_update_employee_empty_name_rejected(self):
        emp = make_employee(self.project.id)
        ok, msg = employee_service.update_employee(
            employee_id=emp.id, project_id=self.project.id,
            code=emp.code, name="   ",
        )
        self.assertFalse(ok)

    def test_delete_employee(self):
        emp = make_employee(self.project.id)
        ok, msg = employee_service.delete_employee(emp.id, self.project.id)
        self.assertTrue(ok, msg)

        db = get_db()
        try:
            self.assertIsNone(db.query(Employee).filter(Employee.id == emp.id).first())
        finally:
            db.close()

    def test_delete_nonexistent_employee_fails_gracefully(self):
        ok, msg = employee_service.delete_employee(999999, self.project.id)
        self.assertFalse(ok)

    def test_next_employee_code_increments(self):
        make_employee(self.project.id, code="E001")
        make_employee(self.project.id, code="E002")
        suggested = employee_service.next_employee_code()
        self.assertEqual(suggested, "E003")


class TestEmployeeProjectIsolation(unittest.TestCase):
    """Phase 4A Step 5 / audit-found bug: 'Project A cannot modify or
    delete Project B's data', enforced at the service/query level, not
    just via UI filtering."""

    def setUp(self):
        reset_session_state()
        self.project_a = make_project()
        self.project_b = make_project()
        self.emp_b = make_employee(self.project_b.id, name="Belongs To B")

    def test_project_a_cannot_update_project_b_employee(self):
        ok, msg = employee_service.update_employee(
            employee_id=self.emp_b.id, project_id=self.project_a.id,
            code=self.emp_b.code, name="Hijacked Name",
        )
        self.assertFalse(ok)

        db = get_db()
        try:
            still = db.query(Employee).filter(Employee.id == self.emp_b.id).first()
            self.assertEqual(still.name, "Belongs To B")
        finally:
            db.close()

    def test_project_a_cannot_delete_project_b_employee(self):
        ok, msg = employee_service.delete_employee(self.emp_b.id, self.project_a.id)
        self.assertFalse(ok)

        db = get_db()
        try:
            self.assertIsNotNone(db.query(Employee).filter(Employee.id == self.emp_b.id).first())
        finally:
            db.close()

    def test_list_employees_never_leaks_other_project(self):
        make_employee(self.project_a.id)
        emps_a = employee_service.list_employees(self.project_a.id)
        self.assertTrue(all(e.project_id == self.project_a.id for e in emps_a))
        self.assertNotIn(self.emp_b.id, [e.id for e in emps_a])


class TestFindSimilarEmployeeName(unittest.TestCase):
    """Regression tests for the gap where create_employee()/update_employee()
    only checked `code` for uniqueness, never `name` — so an alef-variant
    typo like 'شريف أبو العزم' vs an existing 'شريف ابو العزم' was silently
    accepted as two separate employees with no warning at all."""

    def setUp(self):
        reset_session_state()
        self.project = make_project()

    def test_detects_alef_hamza_variant_duplicate(self):
        make_employee(self.project.id, code=unique("SH"), name="شريف ابو العزم")
        similar = employee_service.find_similar_employee(self.project.id, "شريف أبو العزم")
        self.assertIsNotNone(similar)

    def test_no_match_for_genuinely_different_name(self):
        make_employee(self.project.id, code=unique("SH"), name="شريف ابو العزم")
        similar = employee_service.find_similar_employee(self.project.id, "محمد أحمد علي")
        self.assertIsNone(similar)

    def test_does_not_match_across_other_projects(self):
        make_employee(self.project.id, code=unique("SH"), name="شريف ابو العزم")
        other_project = make_project()
        similar = employee_service.find_similar_employee(other_project.id, "شريف أبو العزم")
        self.assertIsNone(similar)

    def test_exclude_id_lets_editing_the_same_employee_pass(self):
        emp = make_employee(self.project.id, code=unique("SH"), name="شريف ابو العزم")
        similar = employee_service.find_similar_employee(
            self.project.id, "شريف أبو العزم", exclude_id=emp.id
        )
        self.assertIsNone(similar)


if __name__ == "__main__":
    unittest.main()
