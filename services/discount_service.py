"""
Discount CRUD + calculation service.

Mirrors the shape of services/advance_service.py (same project-scope
enforcement pattern, same payroll-cache invalidation on every write), but
adds the piece advances don't need: computing the deducted EGP `amount`
from one of three discount types, using the exact same rate formulas
already used elsewhere in the app (services/rates.py) so a discounted
hour is always priced the same as an overtime hour.

DISCOUNT_TYPES
──────────────
  'amount'    — a fixed EGP value entered directly by HR.
  'half_day'  — half of the employee's daily rate.
  'hours'     — a number of hours × the employee's hourly rate.
"""
import re
from datetime import date, datetime
from database.db import get_db
from database.models import Discount, Employee
from services.payroll_service import clear_payroll_cache
from services.projects import get_current_project_id
from services.rates import calc_daily_rate, calc_hourly_rate
from services.name_matching import build_employee_name_index, match_employee_by_name
from core.logging_config import get_logger

_log = get_logger(__name__)

DISCOUNT_TYPES = ('amount', 'half_day', 'hours')

DISCOUNT_TYPE_LABELS = {
    'amount':   'مبلغ ثابت',
    'half_day': 'نص يوم',
    'hours':    'عدد ساعات',
}


def _employee_daily_rate(emp: Employee) -> float:
    """Same fallback chain used across the app: explicit daily_rate first,
    otherwise derived from the monthly salary."""
    if emp.daily_rate and emp.daily_rate > 0:
        return emp.daily_rate
    return calc_daily_rate(emp.salary or 0.0)


def compute_discount_amount(emp: Employee, discount_type: str, value: float = 0.0) -> tuple[float, float]:
    """
    Compute the final EGP deduction for one employee.

    Returns (amount, rate_snapshot):
      - amount:        the EGP value to deduct from that employee's payroll.
      - rate_snapshot: the daily/hourly rate actually used (0.0 for
                        'amount', since no rate is involved) — stored on
                        the record so it survives later salary changes.
    """
    if discount_type == 'amount':
        return max(float(value or 0.0), 0.0), 0.0

    if discount_type == 'half_day':
        daily = _employee_daily_rate(emp)
        return round(daily / 2.0, 2), round(daily, 2)

    if discount_type == 'hours':
        hourly = calc_hourly_rate(emp)
        hours = max(float(value or 0.0), 0.0)
        return round(hours * hourly, 2), hourly

    raise ValueError(f"نوع خصم غير معروف: {discount_type}")


def create_discounts_bulk(
    project_id: int, employee_ids: list[int], disc_date, discount_type: str,
    value: float = 0.0, notes: str = '', created_by: int = None,
) -> tuple[bool, str, float]:
    """
    Create one Discount row per employee in `employee_ids`, each priced
    off that employee's OWN rate (so a mixed selection of employees with
    different salaries still gets a correct, individual deduction).

    Returns (success, message, total_amount_deducted).
    """
    if discount_type not in DISCOUNT_TYPES:
        return False, "نوع الخصم غير صالح.", 0.0
    if not employee_ids:
        return False, "يرجى اختيار موظف واحد على الأقل.", 0.0
    if discount_type in ('amount', 'hours') and (value is None or value <= 0):
        label = "المبلغ" if discount_type == 'amount' else "عدد الساعات"
        return False, f"{label} يجب أن يكون أكبر من صفر.", 0.0

    db = get_db()
    try:
        employees = db.query(Employee).filter(
            Employee.id.in_(employee_ids), Employee.project_id == project_id,
        ).all()
        if not employees:
            return False, "لم يتم العثور على الموظفين المحددين في هذا المشروع.", 0.0

        existing_employee_ids = {
            row.employee_id for row in db.query(Discount.employee_id).filter(
                Discount.employee_id.in_([employee.id for employee in employees]),
                Discount.date == disc_date,
                Discount.discount_type == discount_type,
                Discount.project_id == project_id,
            ).all()
        }
        duplicate_names = [employee.name for employee in employees if employee.id in existing_employee_ids]
        total = 0.0
        created = 0
        for emp in employees:
            if emp.id in existing_employee_ids:
                continue
            amount, rate_snapshot = compute_discount_amount(emp, discount_type, value)
            if amount <= 0:
                continue
            db.add(Discount(
                employee_id=emp.id, date=disc_date, discount_type=discount_type,
                hours=float(value or 0.0) if discount_type == 'hours' else 0.0,
                rate_snapshot=rate_snapshot, amount=amount, notes=notes,
                created_by=created_by, project_id=project_id,
            ))
            total += amount
            created += 1

        if created == 0:
            if duplicate_names:
                return False, (
                    "لم يتم تسجيل أي خصم: يوجد خصم بنفس النوع والتاريخ بالفعل للموظف/الموظفين: "
                    + "، ".join(duplicate_names)
                ), 0.0
            return False, "تعذر احتساب قيمة الخصم — تأكد أن الموظفين المختارين لديهم راتب أو معدل يومي مسجل.", 0.0

        db.commit()
        clear_payroll_cache()
        _log.info(
            "Discounts created: count=%s type=%s date=%s project_id=%s total=%s",
            created, discount_type, disc_date, project_id, total,
        )
        plural = "موظف" if created == 1 else "موظفين"
        message = f"تم تسجيل الخصم لعدد {created} {plural} بإجمالي {total:,.2f} ج.م ✅"
        if duplicate_names:
            message += " — تم تجاهل خصم مكرر لـ: " + "، ".join(duplicate_names)
        return True, message, total
    except Exception as e:
        db.rollback()
        _log.exception("Bulk discount creation failed for project_id=%s", project_id)
        return False, f"خطأ: {e}", 0.0
    finally:
        db.close()


def update_discount(
    record_id: int, project_id: int, employee_id: int, disc_date,
    discount_type: str, value: float = 0.0, notes: str = '',
) -> tuple[bool, str]:
    """Edit a single discount record, identified by primary key.
    `project_id` must match the record's own stored project_id."""
    if discount_type not in DISCOUNT_TYPES:
        return False, "نوع الخصم غير صالح."
    db = get_db()
    try:
        obj = db.query(Discount).filter(
            Discount.id == record_id, Discount.project_id == project_id,
        ).first()
        if not obj:
            return False, "السجل غير موجود أو لا يخص هذا المشروع."

        duplicate = db.query(Discount).filter(
            Discount.employee_id == employee_id,
            Discount.date == disc_date,
            Discount.discount_type == discount_type,
            Discount.project_id == project_id,
            Discount.id != record_id,
        ).first()
        if duplicate:
            return False, "يوجد خصم بنفس النوع والتاريخ لهذا الموظف بالفعل."

        emp = db.query(Employee).filter(
            Employee.id == employee_id, Employee.project_id == project_id,
        ).first()
        if not emp:
            return False, "الموظف غير موجود في هذا المشروع."

        amount, rate_snapshot = compute_discount_amount(emp, discount_type, value)
        if amount <= 0:
            return False, "قيمة الخصم المحسوبة صفر — تحقق من القيمة المدخلة أو راتب الموظف."

        obj.employee_id = employee_id
        obj.date = disc_date
        obj.discount_type = discount_type
        obj.hours = float(value or 0.0) if discount_type == 'hours' else 0.0
        obj.rate_snapshot = rate_snapshot
        obj.amount = amount
        obj.notes = notes
        db.commit()
        clear_payroll_cache()
        _log.info("Discount updated: id=%s project_id=%s", record_id, project_id)
        return True, "تم تحديث الخصم بنجاح."
    except Exception as e:
        db.rollback()
        _log.exception("Discount update failed for id=%s", record_id)
        return False, f"خطأ: {e}"
    finally:
        db.close()


def delete_discount(record_id: int, project_id: int) -> tuple[bool, str]:
    """Delete ONE discount record by primary key, scoped to `project_id`."""
    db = get_db()
    try:
        obj = db.query(Discount).filter(
            Discount.id == record_id, Discount.project_id == project_id,
        ).first()
        if not obj:
            return False, "السجل غير موجود أو لا يخص هذا المشروع."
        db.delete(obj)
        db.commit()
        clear_payroll_cache()
        _log.info("Discount deleted: id=%s project_id=%s", record_id, project_id)
        return True, "تم حذف الخصم."
    except Exception as e:
        db.rollback()
        _log.exception("Discount delete failed for id=%s", record_id)
        return False, f"خطأ في الحذف: {e}"
    finally:
        db.close()


# ── Smart Paste (additive — mirrors the smart-input tabs already used
# in Attendance and Bulk Overtime; does not change any existing
# behavior of create_discounts_bulk/update_discount/delete_discount
# above) ─────────────────────────────────────────────────────────────
#
# Expected pasted format:
#   line 1  -> date (DD/MM/YYYY, also accepts Arabic-Indic digits)
#   line 2  -> discount type + value, recognized as free text:
#                "نص يوم" / "نصف يوم"      -> half_day (no value needed)
#                "<number> ساعة/ساعات"     -> hours, value = number
#                "<number>" (or "... جنيه") -> amount, value = number
#   remaining lines -> one employee name per line. A trailing "+N" adds
#                N to that employee's own value (extra hours/EGP on top
#                of the line-2 base) — meaningless for half_day and
#                therefore ignored for that type.

_DISC_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_DISC_BONUS_RE  = re.compile(r'\+\s*(\d+(?:\.\d+)?)\s*$')
_DISC_NUM_RE    = re.compile(r'(\d+(?:\.\d+)?)')
_DISC_HALF_RE   = re.compile(r'نص\s*يوم|نصف\s*يوم')
_DISC_HOURS_RE  = re.compile(r'ساعات|ساعة|hours?', re.IGNORECASE)


def _disc_normalize_digits(s: str) -> str:
    return s.translate(_DISC_AR_DIGITS)


def _parse_discount_type_line(line: str):
    """Parse line 2 (\"نص يوم\" / \"2 ساعة\" / \"100 جنيه\") into
    (discount_type, base_value) or (None, None) if unrecognized."""
    norm = _disc_normalize_digits(line).strip()
    if _DISC_HALF_RE.search(norm):
        return 'half_day', 0.0
    m = _DISC_NUM_RE.search(norm)
    if not m:
        return None, None
    value = float(m.group(1))
    if _DISC_HOURS_RE.search(norm):
        return 'hours', value
    return 'amount', value


def _parse_discount_name_line(line: str):
    """Parse one employee line, extracting the optional trailing \"+N\" bonus.
      \"محمود فتحي+50\" -> {name: \"محمود فتحي\", bonus: 50.0}
      \"محمود فتحي\"     -> {name: \"محمود فتحي\", bonus: 0.0}"""
    line = _disc_normalize_digits(line).strip()
    if not line:
        return None
    bonus = 0.0
    m = _DISC_BONUS_RE.search(line)
    if m:
        bonus = float(m.group(1))
        line = line[:m.start()].strip()
    name = re.sub(r'\s+', ' ', line).strip()
    if not name:
        return None
    return {"name": name, "bonus": bonus}


def parse_smart_discount_text(text: str):
    """
    Parse the smart-paste discount format.

    Returns: (disc_date | None, discount_type | None, base_value | None,
              entries: list[{name, bonus}], errors: list[str])
    """
    raw_lines = [l.strip() for l in text.strip().splitlines()]
    lines = [l for l in raw_lines if l]

    if len(lines) < 2:
        return None, None, None, [], ['النص غير مكتمل: يجب أن يحتوي على سطر تاريخ وسطر نوع الخصم على الأقل']

    date_line = _disc_normalize_digits(lines[0])
    disc_date = None
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y'):
        try:
            disc_date = datetime.strptime(date_line, fmt).date()
            break
        except ValueError:
            continue
    if disc_date is None:
        return None, None, None, [], [f'تنسيق التاريخ غير صحيح: {lines[0]}']

    discount_type, base_value = _parse_discount_type_line(lines[1])
    if discount_type is None:
        return disc_date, None, None, [], [f'لم يتم التعرف على نوع/قيمة الخصم: {lines[1]}']

    entries = []
    for line in lines[2:]:
        parsed = _parse_discount_name_line(line)
        if parsed:
            entries.append(parsed)

    if not entries:
        return disc_date, discount_type, base_value, [], ['لم يتم العثور على أسماء صالحة في النص']

    return disc_date, discount_type, base_value, entries, []


def process_smart_discount(text: str, created_by: int = None):
    """
    Parse smart-paste discount text and save one Discount row per matched,
    non-duplicate employee — each priced off that employee's OWN rate,
    exactly like create_discounts_bulk() above.

    Returns a result dict compatible with the UI (mirrors
    process_smart_attendance's shape): success, date, discount_type,
    matched, unmatched, duplicates (list), saved (int), total (float).
    """
    disc_date, discount_type, base_value, entries, errors = parse_smart_discount_text(text)
    if errors:
        return {'success': False, 'errors': errors}

    project_id = get_current_project_id()
    db = get_db()
    try:
        employees = db.query(Employee).filter(
            Employee.status == 'Active', Employee.project_id == project_id,
        ).all()
        name_index = build_employee_name_index(employees)

        matched, unmatched, duplicates = [], [], []
        saved = 0
        total = 0.0
        seen_in_batch = set()

        for entry in entries:
            emp, _status = match_employee_by_name(entry['name'], name_index=name_index)
            if not emp:
                unmatched.append(entry['name'])
                continue

            value = base_value + entry['bonus'] if discount_type != 'half_day' else base_value
            amount, rate_snapshot = compute_discount_amount(emp, discount_type, value)
            if amount <= 0:
                unmatched.append(entry['name'])
                continue

            already_exists = db.query(Discount).filter(
                Discount.employee_id == emp.id,
                Discount.date == disc_date,
                Discount.discount_type == discount_type,
                Discount.project_id == project_id,
            ).first()
            if already_exists or emp.id in seen_in_batch:
                duplicates.append(emp.name)
                continue

            db.add(Discount(
                employee_id=emp.id, date=disc_date, discount_type=discount_type,
                hours=float(value or 0.0) if discount_type == 'hours' else 0.0,
                rate_snapshot=rate_snapshot, amount=amount, notes='لصق نص ذكي',
                created_by=created_by, project_id=project_id,
            ))
            seen_in_batch.add(emp.id)
            matched.append(emp.name)
            saved += 1
            total += amount

        db.commit()
        clear_payroll_cache()
        _log.info(
            "Smart-paste discounts saved: count=%s type=%s date=%s project_id=%s total=%s",
            saved, discount_type, disc_date, project_id, total,
        )
        return {
            'success':       True,
            'date':          disc_date,
            'discount_type': discount_type,
            'matched':       matched,
            'unmatched':     unmatched,
            'duplicates':    duplicates,
            'saved':         saved,
            'total':         total,
        }
    except Exception as e:
        db.rollback()
        _log.exception("Smart-paste discount save failed for project_id=%s", project_id)
        return {'success': False, 'errors': [str(e)]}
    finally:
        db.close()
