"""
Employee CRUD service.

Extracted from page_modules/employees.py (Phase 4A backend decoupling) so
the business rules for creating/editing/deleting an employee live in
exactly one place, reusable by both the Streamlit UI and the future
PySide6 desktop UI (see Phase 4A Step 2 — "The PySide6 UI must NOT
duplicate ... employee ... business logic").

Two real bugs found during the Phase 4A audit and fixed here:

1. **Missing project-scope enforcement at the query level.** The original
   `page_modules/employees.py` edit/delete code looked employees up by
   `Employee.id == emp_id` alone — the project boundary was enforced only
   by the fact that the UI's dropdown had been built from an
   already-project-filtered list. Every write function below re-checks
   `Employee.project_id == project_id` itself, matching the pattern
   `services/attendance_service.py` already uses correctly
   (`update_attendance_record` / `delete_attendance_record`), so a stale
   or mixed-up employee id can never edit/delete another project's
   employee even if the caller passes the wrong id.

2. **Missing payroll-cache invalidation.** Editing an employee's
   `daily_rate`/`salary`/`status` (which changes payroll: base salary,
   which employees payroll includes) or deleting an employee never
   called `clear_payroll_cache()` — this was flagged as a known,
   unfixed issue in the Phase 3 report ("Employee-level payroll
   staleness"). Every write path below now calls it, mirroring how
   attendance/overtime/advance writes already did.
"""
import re
from datetime import date
from database.db import get_db
from database.models import Employee
from services.payroll_service import clear_payroll_cache
from services.name_matching import normalize_arabic_name
from core.logging_config import get_logger

_log = get_logger(__name__)

_CODE_RE = re.compile(r'^([A-Za-z\u0600-\u06FF]*)(\d+)$')


def next_employee_code(db=None) -> str:
    """
    Suggest the next employee code based on the codes already in the DB —
    e.g. if the highest existing code is E040, suggest E041. Falls back to
    "E001" when there are no employees yet, or when no existing code
    matches the "letters + digits" pattern (a free-form code was used).
    Keeps the same zero-padding width as the highest matched code (so
    E007 → E008, but E0099 → E0100), and skips forward past any code
    that already exists, in case of gaps or manual overrides.

    Employee codes are unique across the whole installation (not per
    project), matching the existing `Employee.code` unique constraint —
    so this looks at every employee, not just the current project's.
    """
    owns_session = db is None
    db = db or get_db()
    try:
        codes = [c for (c,) in db.query(Employee.code).all() if c]
        best_num, best_width, best_prefix = 0, 3, "E"
        for code in codes:
            m = _CODE_RE.match(code.strip())
            if not m:
                continue
            prefix, num_str = m.groups()
            num = int(num_str)
            if num > best_num:
                best_num, best_width, best_prefix = num, len(num_str), (prefix or "E")

        existing = set(codes)
        next_num = best_num + 1
        candidate = f"{best_prefix}{str(next_num).zfill(best_width)}"
        while candidate in existing:
            next_num += 1
            candidate = f"{best_prefix}{str(next_num).zfill(best_width)}"
        return candidate
    finally:
        if owns_session:
            db.close()


def list_employees(project_id: int, status: str = None):
    """List employees scoped to one project, optionally filtered by
    status ('Active' / 'Inactive' / 'Suspended')."""
    db = get_db()
    try:
        q = db.query(Employee).filter(Employee.project_id == project_id)
        if status:
            q = q.filter(Employee.status == status)
        return q.order_by(Employee.code).all()
    finally:
        db.close()


def find_similar_employee(project_id: int, name: str, exclude_id: int = None):
    """
    Look for an existing employee in the same project whose name
    normalizes (see services.name_matching.normalize_arabic_name — the
    same diacritics/alef-variant/whitespace normalization already used
    for smart-paste attendance/overtime matching) to the same value as
    `name`.

    This is the fix for a real gap: create_employee()/update_employee()
    only ever enforced uniqueness on `code`, never on `name` — so typing
    "شريف أبو العزم" for an employee already saved as "شريف ابو العزم"
    (differ only by أ vs ا, i.e. an alef-variant/hamza spelling) was
    silently accepted as a second, separate employee with no warning at
    all.

    Used by the Add/Edit Employee forms to warn about a likely duplicate
    entry before saving. Returns the matching Employee, or None if no
    same-project employee (other than `exclude_id`, when editing)
    normalizes to the same name. Deliberately NEVER used to block saving
    by itself — it's entirely possible for two different real people to
    share a name, so the caller must let the user confirm and proceed.
    """
    target = normalize_arabic_name(name)
    if not target:
        return None
    db = get_db()
    try:
        q = db.query(Employee).filter(Employee.project_id == project_id)
        if exclude_id is not None:
            q = q.filter(Employee.id != exclude_id)
        for emp in q.all():
            if normalize_arabic_name(emp.name) == target:
                return emp
        return None
    finally:
        db.close()


def create_employee(
    project_id: int, code: str, name: str, job_title: str = '', department: str = '',
    salary: float = 0.0, daily_rate: float = 0.0, phone: str = '', national_id: str = '',
    area: str = '', hire_date: date = None, status: str = 'Active',
) -> tuple[bool, str]:
    """Create a new employee, scoped to `project_id`. Returns (success, message)."""
    code = (code or '').strip()
    name = (name or '').strip()
    if not code or not name:
        return False, "الكود والاسم حقول إجبارية."

    db = get_db()
    try:
        existing = db.query(Employee).filter(Employee.code == code).first()
        if existing:
            return False, f"الكود «{code}» مستخدم مسبقاً، اختر كوداً آخر."

        db.add(Employee(
            code=code, name=name, job_title=job_title, department=department,
            salary=salary, daily_rate=daily_rate, phone=phone, national_id=national_id,
            area=area, hire_date=hire_date, status=status, project_id=project_id,
        ))
        db.commit()
        _log.info("Employee created: code=%s project_id=%s", code, project_id)
        return True, f"تم إضافة الموظف {name} بنجاح! 🎉"
    except Exception as e:
        db.rollback()
        _log.exception("Employee creation failed for code=%s", code)
        return False, f"خطأ غير متوقع: {e}"
    finally:
        db.close()


def update_employee(
    employee_id: int, project_id: int, code: str, name: str, job_title: str = '',
    department: str = '', salary: float = 0.0, daily_rate: float = 0.0, phone: str = '',
    national_id: str = '', area: str = '', status: str = 'Active',
) -> tuple[bool, str]:
    """
    Edit an employee, identified by primary key. `project_id` must match
    the record's own stored project_id, or the update is refused — this
    is the project-isolation guard rail (see module docstring, bug #1).

    Invalidates the payroll cache on every successful update, since
    editing salary/daily_rate/status can change payroll results for this
    employee immediately (see module docstring, bug #2).
    """
    name = (name or '').strip()
    if not name:
        return False, "الاسم لا يمكن أن يكون فارغاً."

    db = get_db()
    try:
        obj = db.query(Employee).filter(
            Employee.id == employee_id,
            Employee.project_id == project_id,
        ).first()
        if not obj:
            return False, "الموظف غير موجود أو لا يخص هذا المشروع."

        obj.code = code
        obj.name = name
        obj.job_title = job_title
        obj.department = department
        obj.salary = salary
        obj.daily_rate = daily_rate
        obj.phone = phone
        obj.national_id = national_id
        obj.area = area
        obj.status = status
        db.commit()
        clear_payroll_cache()
        _log.info("Employee updated: id=%s project_id=%s", employee_id, project_id)
        return True, "تم تحديث بيانات الموظف بنجاح. ✅"
    except Exception as e:
        db.rollback()
        _log.exception("Employee update failed for id=%s", employee_id)
        return False, f"خطأ: {e}"
    finally:
        db.close()


def delete_employee(employee_id: int, project_id: int) -> tuple[bool, str]:
    """
    Delete an employee, identified by primary key. `project_id` must
    match the record's own stored project_id, or nothing is deleted (see
    module docstring, bug #1). The model's cascade='all, delete-orphan'
    relationships take care of removing this employee's
    attendance/overtime/advance/payroll-cache rows too.

    Invalidates the payroll cache on every successful delete (see module
    docstring, bug #2) — otherwise a deleted employee could keep
    appearing in payroll for up to the cache TTL.
    """
    db = get_db()
    try:
        obj = db.query(Employee).filter(
            Employee.id == employee_id,
            Employee.project_id == project_id,
        ).first()
        if not obj:
            return False, "الموظف غير موجود أو لا يخص هذا المشروع."
        db.delete(obj)
        db.commit()
        clear_payroll_cache()
        _log.info("Employee deleted: id=%s project_id=%s", employee_id, project_id)
        return True, "تم حذف الموظف بنجاح."
    except Exception as e:
        db.rollback()
        _log.exception("Employee delete failed for id=%s", employee_id)
        return False, f"خطأ في الحذف: {e}"
    finally:
        db.close()
