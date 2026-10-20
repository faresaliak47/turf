"""
Shared pay-rate calculations.

Single source of truth for the hourly-rate formula used across the
Overtime page, Bulk Overtime page, and any future module that needs it.
Previously this logic was copy-pasted in multiple files — a change to the
business rule (e.g. workdays-per-month) had to be remembered in every copy,
which silently drifts. Now there is exactly one place to change it.
"""
from database.models import Employee


def calc_daily_rate(salary: float, workdays_per_month: float = 30.0) -> float:
    """
    Derive a daily rate from a monthly salary: salary ÷ workdays_per_month.

    Used by the Employees page to auto-fill `daily_rate` so HR doesn't
    have to compute and type it in by hand (a common source of typos).

    The application uses a consistent 30-day month for both daily and
    hourly calculations.
    """
    if not salary or salary <= 0 or not workdays_per_month:
        return 0.0
    return round(salary / workdays_per_month, 2)


def calc_hourly_rate(emp: Employee) -> float:
    """
    Compute an employee's (or equipment's, since it's stored as an Employee
    record) hourly overtime rate.

    Rules:
    1. Use emp.daily_rate directly if it's set and > 0.
    2. Otherwise derive it from the monthly salary ÷ 30 days.
    3. Hourly rate = daily rate ÷ 8 working hours.
    """
    if emp.daily_rate and emp.daily_rate > 0:
        daily = emp.daily_rate
    elif emp.salary and emp.salary > 0:
        daily = emp.salary / 30.0
    else:
        daily = 0.0
    return round(daily / 8.0, 4)
