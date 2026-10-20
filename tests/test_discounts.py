"""Duplicate prevention for salary discounts."""
import unittest
from datetime import date

from tests import _bootstrap  # noqa: F401
from tests.helpers import make_project, make_employee, reset_session_state
from services import discount_service


class TestDiscountDuplicatePrevention(unittest.TestCase):
    def setUp(self):
        reset_session_state()
        self.project = make_project()
        self.employee = make_employee(self.project.id, daily_rate=100)
        self.day = date(2026, 5, 7)

    def test_same_employee_date_and_type_is_not_added_twice(self):
        first = discount_service.create_discounts_bulk(
            self.project.id, [self.employee.id], self.day, 'amount', 50,
        )
        self.assertTrue(first[0], first[1])
        second = discount_service.create_discounts_bulk(
            self.project.id, [self.employee.id], self.day, 'amount', 50,
        )
        self.assertFalse(second[0])
        self.assertIn('يوجد خصم', second[1])

    def test_different_discount_type_on_same_day_is_allowed(self):
        self.assertTrue(discount_service.create_discounts_bulk(
            self.project.id, [self.employee.id], self.day, 'amount', 50,
        )[0])
        self.assertTrue(discount_service.create_discounts_bulk(
            self.project.id, [self.employee.id], self.day, 'hours', 1,
        )[0])


if __name__ == '__main__':
    unittest.main()
