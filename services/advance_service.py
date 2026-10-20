"""
Advance CRUD service.

Extracted from page_modules/advances.py and page_modules/expenses.py's
`_save_advance` (Phase 4A backend decoupling) — both call this module now
so there is exactly one place that creates/edits/deletes an Advance
record, reusable by the future PySide6 UI.

Two real bugs found during the Phase 4A audit and fixed here:

1. **Missing project-scope enforcement at the query level** in
   page_modules/advances.py's edit/delete (`Advance.id == rec_id` alone,
   same class of gap as Employees/Overtime — see
   services/employee_service.py's docstring for the general pattern).
   Both functions below enforce `Advance.project_id == project_id`.

2. **Missing payroll-cache invalidation** in two places:
     - page_modules/advances.py's delete path (the edit/save path
       already called `clear_payroll_cache()`, delete did not).
     - page_modules/expenses.py's `_save_advance()` (the Smart Paste
       "advance" entries on the Expenses page never invalidated the
       payroll cache at all).
   Every write path below now calls it.
"""
from database.db import get_db
from database.models import Advance
from services.payroll_service import clear_payroll_cache
from core.logging_config import get_logger

_log = get_logger(__name__)


def create_advance(
    project_id: int, employee_id: int, adv_date, amount: float, notes: str = '',
) -> tuple[bool, str]:
    """Create a new advance record, scoped to `project_id`."""
    if amount is None or amount <= 0:
        return False, "المبلغ يجب أن يكون أكبر من صفر."
    db = get_db()
    try:
        db.add(Advance(
            employee_id=employee_id, date=adv_date, amount=amount, notes=notes,
            project_id=project_id,
        ))
        db.commit()
        clear_payroll_cache()
        _log.info("Advance created: employee_id=%s date=%s project_id=%s", employee_id, adv_date, project_id)
        return True, f"تم تسجيل السلفة بنجاح. المبلغ: {amount:,.2f} ج.م ✅"
    except Exception as e:
        db.rollback()
        _log.exception("Advance creation failed for employee_id=%s", employee_id)
        return False, f"خطأ: {e}"
    finally:
        db.close()


def update_advance(
    record_id: int, project_id: int, employee_id: int, adv_date, amount: float, notes: str = '',
) -> tuple[bool, str]:
    """
    Edit an advance record, identified by primary key. `project_id` must
    match the record's own stored project_id, or the update is refused
    (see module docstring, bug #1).
    """
    db = get_db()
    try:
        obj = db.query(Advance).filter(
            Advance.id == record_id,
            Advance.project_id == project_id,
        ).first()
        if not obj:
            return False, "السجل غير موجود أو لا يخص هذا المشروع."

        obj.employee_id = employee_id
        obj.date = adv_date
        obj.amount = amount
        obj.notes = notes
        db.commit()
        clear_payroll_cache()
        _log.info("Advance updated: id=%s project_id=%s", record_id, project_id)
        return True, "تم تحديث السلفة بنجاح."
    except Exception as e:
        db.rollback()
        _log.exception("Advance update failed for id=%s", record_id)
        return False, f"خطأ: {e}"
    finally:
        db.close()


def delete_advance(record_id: int, project_id: int) -> tuple[bool, str]:
    """
    Delete ONE advance record by primary key. `project_id` must match
    the record's own stored project_id, or nothing is deleted (see
    module docstring, bug #1). Also invalidates the payroll cache (bug
    #2) — the original code did not.
    """
    db = get_db()
    try:
        obj = db.query(Advance).filter(
            Advance.id == record_id,
            Advance.project_id == project_id,
        ).first()
        if not obj:
            return False, "السجل غير موجود أو لا يخص هذا المشروع."
        db.delete(obj)
        db.commit()
        clear_payroll_cache()
        _log.info("Advance deleted: id=%s project_id=%s", record_id, project_id)
        return True, "تم حذف السلفة."
    except Exception as e:
        db.rollback()
        _log.exception("Advance delete failed for id=%s", record_id)
        return False, f"خطأ في الحذف: {e}"
    finally:
        db.close()
