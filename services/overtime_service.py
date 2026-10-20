"""
Overtime CRUD service (edit/delete paths).

Extracted from page_modules/overtime.py (Phase 4A backend decoupling).
The "add" path and its duplicate-handling UI flow stay in the page module
for now, since that flow is tightly coupled to a multi-step Streamlit
confirmation UI (see page_modules/overtime.py's `ot_dup_pending` state) —
splitting only the add-transaction itself out would leave the page module
still duplicating the more important edit/delete safety logic (project
scoping) needed by the future PySide6 UI. The instant next
Streamlit-independent add path can be layered on top of this module in
Phase 4B without changing these functions.

Bug fixed here (Phase 4A audit): `page_modules/overtime.py`'s edit/delete
queried `Overtime.id == rec_id` with no project_id check — the same class
of project-isolation gap as Employees (see services/employee_service.py's
docstring). Both functions below now enforce `Overtime.project_id ==
project_id` at the query level, matching the pattern already used
correctly in services/attendance_service.py.
"""
from database.db import get_db
from database.models import Employee, Overtime
from services.payroll_service import clear_payroll_cache
from core.logging_config import get_logger
from datetime import date
from services.overtime_records import unique_overtime_records

_log = get_logger(__name__)


def get_overtime_matrix(month: int, year: int, department: str = None,
                        project_id: int = None):
    """Build a monthly overtime matrix with one row per active employee.

    Each day cell is the sum of all overtime records for that employee on
    that day. Summing (rather than selecting one record) keeps Excel-imported
    or bulk-entered records accurate when more than one entry exists per day.
    """
    import calendar
    import pandas as pd
    from services.projects import get_current_project_id

    if project_id is None:
        project_id = get_current_project_id()
    days_in_month = calendar.monthrange(year, month)[1]
    start_date = date(year, month, 1)
    end_date = date(year, month, days_in_month)

    db = get_db()
    try:
        employees_query = db.query(Employee).filter(
            Employee.status == 'Active', Employee.project_id == project_id,
        )
        if department:
            employees_query = employees_query.filter(Employee.department == department)
        employees = employees_query.order_by(Employee.name).all()
        if not employees:
            return pd.DataFrame()

        employee_ids = [employee.id for employee in employees]
        records = db.query(Overtime).filter(
            Overtime.employee_id.in_(employee_ids),
            Overtime.project_id == project_id,
            Overtime.date >= start_date,
            Overtime.date <= end_date,
        ).all()
        records = unique_overtime_records(records)

        hours_by_day = {}
        for record in records:
            key = (record.employee_id, record.date.day)
            hours_by_day[key] = hours_by_day.get(key, 0.0) + (record.hours or 0.0)

        rows = []
        for employee in employees:
            row = {'كود الموظف': employee.code, 'اسم الموظف': employee.name}
            for day in range(1, days_in_month + 1):
                row[str(day)] = round(hours_by_day.get((employee.id, day), 0.0), 2)
            row['إجمالي الأوفر تايم'] = round(
                sum(hours_by_day.get((employee.id, day), 0.0) for day in range(1, days_in_month + 1)),
                2,
            )
            rows.append(row)
        return pd.DataFrame(rows)
    finally:
        db.close()


def find_duplicate(employee_id: int, ot_date, exclude_id: int = None,
                   project_id: int = None):
    """Return the existing Overtime record for this employee+date, if
    any (excluding `exclude_id` when editing), or None. Overtime allows
    multiple entries per employee/day in general via Excel import, but
    the manual add/edit UI flow intentionally still warns/blocks on a
    same-day duplicate — this helper centralizes that lookup."""
    db = get_db()
    try:
        q = db.query(Overtime).filter(
            Overtime.employee_id == employee_id,
            Overtime.date == ot_date,
        )
        if project_id is not None:
            q = q.filter(Overtime.project_id == project_id)
        if exclude_id is not None:
            q = q.filter(Overtime.id != exclude_id)
        return q.first()
    finally:
        db.close()


def create_overtime(
    project_id: int, employee_id: int, ot_date, hours: float,
    rate_per_hour: float, amount: float, notes: str = '',
) -> tuple[bool, str]:
    """Create a new overtime record, scoped to `project_id`."""
    db = get_db()
    try:
        duplicate = db.query(Overtime).filter(
            Overtime.employee_id == employee_id,
            Overtime.date == ot_date,
            Overtime.hours == hours,
            Overtime.rate_per_hour == rate_per_hour,
            Overtime.amount == amount,
            Overtime.notes == notes,
            Overtime.project_id == project_id,
        ).first()
        if duplicate:
            return False, "يوجد سجل أوفر تايم مطابق بالفعل لهذا الموظف في نفس التاريخ؛ لم تتم مضاعفة الساعات."
        db.add(Overtime(
            employee_id=employee_id, date=ot_date, hours=hours,
            rate_per_hour=rate_per_hour, amount=amount, notes=notes,
            project_id=project_id,
        ))
        db.commit()
        clear_payroll_cache()
        _log.info("Overtime created: employee_id=%s date=%s project_id=%s", employee_id, ot_date, project_id)
        return True, f"✅ تم حفظ الأوفر تايم بنجاح. المبلغ: {amount:,.2f} ج.م"
    except Exception as e:
        db.rollback()
        _log.exception("Overtime creation failed for employee_id=%s", employee_id)
        return False, f"خطأ: {e}"
    finally:
        db.close()


def replace_overtime(
    record_id: int, project_id: int, employee_id: int, ot_date, hours: float,
    rate_per_hour: float, amount: float, notes: str = '',
) -> tuple[bool, str]:
    """Overwrite an existing overtime record's values in place (the
    'replace duplicate' choice in the add-overtime UI flow). project_id
    must match the record's own stored project_id."""
    db = get_db()
    try:
        obj = db.query(Overtime).filter(
            Overtime.id == record_id,
            Overtime.project_id == project_id,
        ).first()
        if not obj:
            return False, "⚠️ تعذر العثور على السجل الأصلي — ربما تم حذفه. يرجى إعادة المحاولة."
        obj.employee_id = employee_id
        obj.date = ot_date
        obj.hours = hours
        obj.rate_per_hour = rate_per_hour
        obj.amount = amount
        obj.notes = notes
        obj.project_id = project_id
        db.commit()
        clear_payroll_cache()
        _log.info("Overtime replaced: id=%s project_id=%s", record_id, project_id)
        return True, f"✅ تم استبدال السجل الموجود بنجاح. المبلغ: {amount:,.2f} ج.م"
    except Exception as e:
        db.rollback()
        _log.exception("Overtime replace failed for id=%s", record_id)
        return False, f"خطأ أثناء الاستبدال: {e}"
    finally:
        db.close()


def update_overtime(
    record_id: int, project_id: int, employee_id: int, ot_date, hours: float,
    rate_per_hour: float, amount: float, notes: str = '',
) -> tuple[bool, str]:
    """
    Edit an overtime record, identified by primary key. `project_id`
    must match the record's own stored project_id, or the update is
    refused (see module docstring). Re-checks the (employee_id, date)
    duplicate rule against any OTHER record, same as before.
    """
    db = get_db()
    try:
        dup = db.query(Overtime).filter(
            Overtime.employee_id == employee_id,
            Overtime.date == ot_date,
            Overtime.id != record_id,
            Overtime.project_id == project_id,
        ).first()
        if dup:
            return False, (
                f"⚠️ يوجد بالفعل سجل أوفر تايم آخر لهذا الموظف بنفس التاريخ "
                f"({ot_date}، {dup.hours} ساعة). يرجى تعديل التاريخ أو حذف السجل الآخر أولاً."
            )

        obj = db.query(Overtime).filter(
            Overtime.id == record_id,
            Overtime.project_id == project_id,
        ).first()
        if not obj:
            return False, "⚠️ تعذر العثور على السجل — ربما تم حذفه مسبقاً أو لا يخص هذا المشروع."

        obj.employee_id = employee_id
        obj.date = ot_date
        obj.hours = hours
        obj.rate_per_hour = rate_per_hour
        obj.amount = amount
        obj.notes = notes
        obj.project_id = project_id
        db.commit()
        clear_payroll_cache()
        _log.info("Overtime updated: id=%s project_id=%s", record_id, project_id)
        return True, "✅ تم تحديث السجل بنجاح."
    except Exception as e:
        db.rollback()
        _log.exception("Overtime update failed for id=%s", record_id)
        return False, f"حدث خطأ أثناء التحديث: {e}"
    finally:
        db.close()


def delete_overtime(record_id: int, project_id: int) -> tuple[bool, str]:
    """Delete ONE overtime record by primary key. `project_id` must match
    the record's own stored project_id, or nothing is deleted (see
    module docstring)."""
    db = get_db()
    try:
        obj = db.query(Overtime).filter(
            Overtime.id == record_id,
            Overtime.project_id == project_id,
        ).first()
        if not obj:
            return False, "السجل غير موجود أو لا يخص هذا المشروع."
        db.delete(obj)
        db.commit()
        clear_payroll_cache()
        _log.info("Overtime deleted: id=%s project_id=%s", record_id, project_id)
        return True, "✅ تم حذف السجل بنجاح."
    except Exception as e:
        db.rollback()
        _log.exception("Overtime delete failed for id=%s", record_id)
        return False, f"خطأ في الحذف: {e}"
    finally:
        db.close()
