"""
tests/test_advances.py — Advance CRUD + project isolation (Phase 4A
Step 15). Covers services.advance_service (Phase 4A fix for the
audit-found project-scope gap AND the missing clear_payroll_cache() call
on delete / on the Expenses page's Smart Paste flow — see its module
docstring).
"""
import unittest
from tests import _bootstrap  # noqa: F401 — must be first
from tests.helpers import make_project, make_employee, reset_session_state, today

from database.db import get_db
from database.models import Advance
from services import advance_service


class TestAdvanceCRUD(unittest.TestCase):
    def setUp(self):
        reset_session_state()
        self.project = make_project()
        self.emp = make_employee(self.project.id)

    def test_create_advance(self):
        ok, msg = advance_service.create_advance(
            project_id=self.project.id, employee_id=self.emp.id,
            adv_date=today(), amount=500,
        )
        self.assertTrue(ok, msg)
        db = get_db()
        try:
            rec = db.query(Advance).filter(Advance.employee_id == self.emp.id).first()
            self.assertIsNotNone(rec)
            self.assertEqual(rec.amount, 500)
        finally:
            db.close()

    def test_create_advance_rejects_non_positive_amount(self):
        ok, msg = advance_service.create_advance(
            project_id=self.project.id, employee_id=self.emp.id,
            adv_date=today(), amount=0,
        )
        self.assertFalse(ok)

        ok2, msg2 = advance_service.create_advance(
            project_id=self.project.id, employee_id=self.emp.id,
            adv_date=today(), amount=-10,
        )
        self.assertFalse(ok2)

    def test_update_advance(self):
        advance_service.create_advance(
            project_id=self.project.id, employee_id=self.emp.id,
            adv_date=today(), amount=100,
        )
        db = get_db()
        try:
            rec = db.query(Advance).filter(Advance.employee_id == self.emp.id).first()
            rec_id = rec.id
        finally:
            db.close()

        ok, msg = advance_service.update_advance(
            record_id=rec_id, project_id=self.project.id,
            employee_id=self.emp.id, adv_date=today(), amount=250,
        )
        self.assertTrue(ok, msg)

        db = get_db()
        try:
            refreshed = db.query(Advance).filter(Advance.id == rec_id).first()
            self.assertEqual(refreshed.amount, 250)
        finally:
            db.close()

    def test_delete_advance(self):
        advance_service.create_advance(
            project_id=self.project.id, employee_id=self.emp.id,
            adv_date=today(), amount=100,
        )
        db = get_db()
        try:
            rec = db.query(Advance).filter(Advance.employee_id == self.emp.id).first()
            rec_id = rec.id
        finally:
            db.close()

        ok, msg = advance_service.delete_advance(rec_id, self.project.id)
        self.assertTrue(ok, msg)

        db = get_db()
        try:
            self.assertIsNone(db.query(Advance).filter(Advance.id == rec_id).first())
        finally:
            db.close()


class TestAdvanceProjectIsolation(unittest.TestCase):
    def setUp(self):
        reset_session_state()
        self.project_a = make_project()
        self.project_b = make_project()
        self.emp_b = make_employee(self.project_b.id)
        advance_service.create_advance(
            project_id=self.project_b.id, employee_id=self.emp_b.id,
            adv_date=today(), amount=777,
        )
        db = get_db()
        try:
            self.rec_b_id = db.query(Advance).filter(Advance.employee_id == self.emp_b.id).first().id
        finally:
            db.close()

    def test_project_a_cannot_update_project_b_advance(self):
        ok, msg = advance_service.update_advance(
            record_id=self.rec_b_id, project_id=self.project_a.id,
            employee_id=self.emp_b.id, adv_date=today(), amount=1,
        )
        self.assertFalse(ok)
        db = get_db()
        try:
            still = db.query(Advance).filter(Advance.id == self.rec_b_id).first()
            self.assertEqual(still.amount, 777)
        finally:
            db.close()

    def test_project_a_cannot_delete_project_b_advance(self):
        ok, msg = advance_service.delete_advance(self.rec_b_id, self.project_a.id)
        self.assertFalse(ok)
        db = get_db()
        try:
            self.assertIsNotNone(db.query(Advance).filter(Advance.id == self.rec_b_id).first())
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
