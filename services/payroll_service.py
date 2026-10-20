import calendar
from datetime import date
import pandas as pd
from database.db import get_db
from database.models import Employee, Attendance, Overtime, Advance, Discount, PayrollCache
from services.projects import get_current_project_id
from core.cache import cached_data
from core.config import PAYROLL_CACHE_TTL
from services.overtime_records import unique_overtime_records


@cached_data(ttl=PAYROLL_CACHE_TTL, show_spinner=False)
def _calculate_payroll_cached(month: int, year: int, project_id: int) -> pd.DataFrame:
    """Cached core of calculate_payroll(). IMPORTANT: project_id must be
    resolved by the caller (calculate_payroll below) before this is
    invoked — the cache is keyed on the arguments it actually receives,
    so resolving "current project" *inside* a cached function would
    freeze the cache to whatever project was selected the first time it
    ran, and switching projects would silently keep showing the old
    project's payroll."""
    db = get_db()
    try:
        days_in_month = calendar.monthrange(year, month)[1]
        start_date = date(year, month, 1)
        end_date = date(year, month, days_in_month)
        employees = db.query(Employee).filter(
            Employee.status == 'Active', Employee.project_id == project_id
        ).all()
        if not employees:
            return pd.DataFrame()
        emp_ids = [e.id for e in employees]
        att_records = db.query(Attendance).filter(
            Attendance.employee_id.in_(emp_ids),
            Attendance.attendance_date >= start_date,
            Attendance.attendance_date <= end_date,
            Attendance.status == 1,
            Attendance.project_id == project_id,
        ).all()
        att_count = {}
        for r in att_records:
            att_count[r.employee_id] = att_count.get(r.employee_id, 0) + 1
        ot_records = db.query(Overtime).filter(
            Overtime.employee_id.in_(emp_ids),
            Overtime.date >= start_date,
            Overtime.date <= end_date,
            Overtime.project_id == project_id,
        ).all()
        ot_records = unique_overtime_records(ot_records)
        ot_total = {}
        for r in ot_records:
            ot_total[r.employee_id] = ot_total.get(r.employee_id, 0) + (r.amount or 0)
        adv_records = db.query(Advance).filter(
            Advance.employee_id.in_(emp_ids),
            Advance.date >= start_date,
            Advance.date <= end_date,
            Advance.project_id == project_id,
        ).all()
        adv_total = {}
        for r in adv_records:
            adv_total[r.employee_id] = adv_total.get(r.employee_id, 0) + (r.amount or 0)
        disc_records = db.query(Discount).filter(
            Discount.employee_id.in_(emp_ids),
            Discount.date >= start_date,
            Discount.date <= end_date,
            Discount.project_id == project_id,
        ).all()
        disc_total = {}
        for r in disc_records:
            disc_total[r.employee_id] = disc_total.get(r.employee_id, 0) + (r.amount or 0)
        rows = []
        for emp in employees:
            att_days = att_count.get(emp.id, 0)
            ot = ot_total.get(emp.id, 0.0)
            adv = adv_total.get(emp.id, 0.0)
            disc = disc_total.get(emp.id, 0.0)
            base = att_days * (emp.daily_rate or 0)
            net = base + ot - adv - disc
            rows.append({
                'كود الموظف': emp.code,
                'اسم الموظف': emp.name,
                'القسم': emp.department or '',
                'أيام الحضور': att_days,
                'المعدل اليومي': emp.daily_rate or 0,
                'الراتب الأساسي': base,
                'الأوفر تايم': ot,
                'السلف': adv,
                'الخصومات': disc,
                'صافي الراتب': net
            })
        return pd.DataFrame(rows)
    finally:
        db.close()


def calculate_payroll(month: int, year: int, project_id: int = None) -> pd.DataFrame:
    """Public entry point — resolves "current project" here (outside the
    cache) so switching projects always produces a fresh cache key."""
    if project_id is None:
        project_id = get_current_project_id()
    return _calculate_payroll_cached(month, year, project_id)


def clear_payroll_cache():
    """
    Invalidate the payroll calculation cache.

    MUST be called right after any commit that changes Attendance,
    Overtime, or Advance rows (add/edit/delete, single record, bulk
    delete-by-day/month, or Excel import) — otherwise
    `_calculate_payroll_cached`'s `ttl=20` cache can keep serving a
    stale payroll for up to 20 seconds after the underlying data
    changed. The ttl is kept as a safety net only; this explicit
    invalidation is what actually guarantees "no stale payroll after a
    data change" (see PAYROLL CACHE requirements).

    Safe to call even if nothing is cached yet (`.clear()` is a no-op in
    that case), and safe to call from outside a Streamlit script run
    (used by services with no UI, e.g. Excel import, and by the PySide6
    desktop app) since it only touches the cache storage, not the
    session.
    """
    _calculate_payroll_cached.clear()


def save_payroll_cache(month: int, year: int, project_id: int = None):
    """Save calculated payroll to cache table, scoped to a project
    (defaults to the currently-selected one)."""
    if project_id is None:
        project_id = get_current_project_id()
    df = calculate_payroll(month, year, project_id)
    if df.empty:
        return
    db = get_db()
    try:
        employees = {e.code: e.id for e in db.query(Employee).filter(Employee.project_id == project_id).all()}
        for _, row in df.iterrows():
            emp_id = employees.get(row['كود الموظف'])
            if not emp_id:
                continue
            existing = db.query(PayrollCache).filter(
                PayrollCache.employee_id == emp_id,
                PayrollCache.month == month,
                PayrollCache.year == year
            ).first()
            if existing:
                existing.attendance_days = row['أيام الحضور']
                existing.daily_rate = row['المعدل اليومي']
                existing.base_salary = row['الراتب الأساسي']
                existing.overtime = row['الأوفر تايم']
                existing.advances = row['السلف']
                existing.discounts = row['الخصومات']
                existing.net_salary = row['صافي الراتب']
                existing.project_id = project_id
            else:
                pc = PayrollCache(
                    employee_id=emp_id, month=month, year=year,
                    attendance_days=row['أيام الحضور'],
                    daily_rate=row['المعدل اليومي'],
                    base_salary=row['الراتب الأساسي'],
                    overtime=row['الأوفر تايم'],
                    advances=row['السلف'],
                    discounts=row['الخصومات'],
                    net_salary=row['صافي الراتب'],
                    project_id=project_id,
                )
                db.add(pc)
        db.commit()
    except Exception as e:
        print(f"[payroll] Error saving payroll: {e}")
        db.rollback()
        raise
    finally:
        db.close()
