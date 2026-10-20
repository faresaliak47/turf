"""Focused coverage for project-scoped attendance save/overwrite behavior."""
import unittest
from datetime import date

from tests import _bootstrap  # noqa: F401
from tests.helpers import make_project, make_employee, reset_session_state, unique
from core.state import state_set
from database.db import get_db
from database.models import Attendance
from services import attendance_service


class TestAttendanceDuplicateConfirmation(unittest.TestCase):
    def setUp(self):
        reset_session_state()
        self.project = make_project()
        state_set('current_project_id', self.project.id)
        self.employee = make_employee(
            self.project.id, code=unique('ATT'), name='Attendance Test', status='Active'
        )
        self.day = date(2026, 8, 20)

    def _record(self):
        db = get_db()
        try:
            return db.query(Attendance).filter(
                Attendance.employee_id == self.employee.id,
                Attendance.project_id == self.project.id,
                Attendance.attendance_date == self.day,
            ).one()
        finally:
            db.close()

    def test_new_normal_attendance_is_saved(self):
        result = attendance_service.process_attendance('20/08/2026\nAttendance Test')
        self.assertTrue(result['success'])
        self.assertEqual(result['saved'], 1)
        self.assertEqual(result['updated'], 0)

    def test_existing_normal_attendance_requires_confirmation_and_reject_keeps_old(self):
        self.test_new_normal_attendance_is_saved()
        db = get_db()
        try:
            record = db.query(Attendance).filter(Attendance.employee_id == self.employee.id).one()
            record.status, record.workers_count = 0, 4.0
            db.commit()
        finally:
            db.close()

        preview = attendance_service.process_attendance('20/08/2026\nAttendance Test')
        self.assertFalse(preview['success'])
        self.assertTrue(preview['requires_confirmation'])
        self.assertEqual(preview['conflicts'][0]['old']['workers_count'], 4.0)
        self.assertEqual(preview['conflicts'][0]['new']['workers_count'], 1.0)

        # Rejecting in the UI makes no second service call; the preview must
        # therefore leave the persisted record unchanged.
        record = self._record()
        self.assertEqual(record.status, 0)
        self.assertEqual(record.workers_count, 4.0)

    def test_confirm_updates_the_existing_normal_record(self):
        self.test_existing_normal_attendance_requires_confirmation_and_reject_keeps_old()
        result = attendance_service.process_attendance(
            '20/08/2026\nAttendance Test', confirm_updates=True
        )
        self.assertTrue(result['success'])
        self.assertEqual(result['saved'], 0)
        self.assertEqual(result['updated'], 1)
        record = self._record()
        self.assertEqual(record.status, 1)
        self.assertEqual(record.workers_count, 1.0)

    def test_existing_smart_attendance_requires_confirmation_then_updates(self):
        initial = attendance_service.process_smart_attendance('20/08/2026\n4 Attendance Test')
        self.assertTrue(initial['success'])
        preview = attendance_service.process_smart_attendance('20/08/2026\n5 Attendance Test')
        self.assertTrue(preview['requires_confirmation'])
        self.assertEqual(preview['conflicts'][0]['old']['workers_count'], 4)
        self.assertEqual(preview['conflicts'][0]['new']['workers_count'], 5)

        result = attendance_service.process_smart_attendance(
            '20/08/2026\n5 Attendance Test', confirm_updates=True
        )
        self.assertTrue(result['success'])
        self.assertEqual(result['updated'], 1)
        self.assertEqual(self._record().workers_count, 5)

    def test_same_employee_and_date_are_allowed_in_two_projects(self):
        other_project = make_project()
        db = get_db()
        try:
            db.add_all([
                Attendance(employee_id=self.employee.id, project_id=self.project.id,
                           attendance_date=self.day, status=1),
                Attendance(employee_id=self.employee.id, project_id=other_project.id,
                           attendance_date=self.day, status=1),
            ])
            db.commit()
            self.assertEqual(db.query(Attendance).filter(
                Attendance.employee_id == self.employee.id,
                Attendance.attendance_date == self.day,
            ).count(), 2)
        finally:
            db.close()


if __name__ == '__main__':
    unittest.main()
