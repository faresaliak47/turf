"""
tests/test_rates.py — Pay-rate formula regression guard (2026-08 payroll
audit: unified `calc_daily_rate`/`calc_hourly_rate` on a single 30-day
month / 8-hour day convention, replacing the old, silently-diverging
26-day divisor that `calc_hourly_rate` used to apply).

Pins down the confirmed policy so it can never regress back to the old
÷26 formula, or drift again between the daily and hourly functions:
  - Month = 30 days, Day = 8 hours.
  - Daily rate  = explicit Employee.daily_rate if set, else salary ÷ 30.
  - Hourly rate = daily rate ÷ 8.
  - No OT premium: calc_hourly_rate() IS the overtime rate, ×1 — callers
    must not multiply it further.
"""
import unittest
from tests import _bootstrap  # noqa: F401 — must be first
from tests.helpers import make_project, make_employee

from services.rates import calc_daily_rate, calc_hourly_rate


class TestRatePolicy(unittest.TestCase):
    def setUp(self):
        self.project = make_project()

    def test_daily_rate_uses_30_day_month(self):
        self.assertEqual(calc_daily_rate(9000), 300.0)   # 9000 / 30
        self.assertEqual(calc_daily_rate(0), 0.0)
        self.assertEqual(calc_daily_rate(None), 0.0)

    def test_hourly_rate_derives_from_salary_via_30_and_8(self):
        """Salary-only employee (no explicit daily_rate): hourly rate
        must come from salary ÷ 30 ÷ 8, not the old salary ÷ 26 ÷ 8."""
        emp = make_employee(self.project.id, daily_rate=0, salary=9000)
        hourly = calc_hourly_rate(emp)
        self.assertEqual(hourly, 37.5)                    # 9000/30/8

        old_26_day_formula = round((9000 / 26.0) / 8.0, 4)
        self.assertNotEqual(
            hourly, old_26_day_formula,
            "calc_hourly_rate regressed back to the old 26-day divisor",
        )

    def test_hourly_rate_uses_explicit_daily_rate_when_set(self):
        emp = make_employee(self.project.id, daily_rate=120, salary=9000)
        self.assertEqual(calc_hourly_rate(emp), 15.0)      # 120/8, ignores salary

    def test_hourly_rate_zero_when_no_rate_data_at_all(self):
        emp = make_employee(self.project.id, daily_rate=0, salary=0)
        self.assertEqual(calc_hourly_rate(emp), 0.0)

    def test_daily_and_hourly_agree_for_the_same_salary_only_employee(self):
        """The bug this whole fix targets: calc_daily_rate and
        calc_hourly_rate must derive from the SAME daily figure for a
        salary-only employee (previously 30-day vs. 26-day, silently
        disagreeing)."""
        emp = make_employee(self.project.id, daily_rate=0, salary=9000)
        daily = calc_daily_rate(emp.salary)
        hourly = calc_hourly_rate(emp)
        self.assertEqual(hourly, round(daily / 8.0, 4))


if __name__ == "__main__":
    unittest.main()
