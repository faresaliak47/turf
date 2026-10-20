import re
from datetime import date, datetime
from database.db import get_db
from database.models import Employee, Attendance
from services.projects import get_current_project_id
from services.payroll_service import clear_payroll_cache
from services.name_matching import build_employee_name_index, match_employee_by_name
import pandas as pd


# ── Arabic/English noise words to strip from name lines ──────────
# These are the "multiplier unit" words that can sit next to a count
# (e.g. "5 عمال أشرف", "3 ع محمد", "2 workers Ali") and must be removed
# from the name without affecting the parsed count.
_NOISE_WORDS = re.compile(
    r'\b(عمال|عامل|موظف|موظفون|مهندس|مساعد|فني|ع|workers?)\b',
    re.UNICODE | re.IGNORECASE,
)

# Arabic-Indic digits (٠-٩) → Western digits (0-9)
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

# Matches an integer or decimal number (accepts "." or "," as the separator),
# anywhere in the line — not just at the start.
_COUNT_RE = re.compile(r'(\d+(?:[.,]\d+)?)')


def normalize_name(name: str) -> str:
    """Remove prefixes and normalize Arabic name for matching."""
    name = name.strip()
    prefixes = ['م ', 'م. ', 'أ. ', 'أ ', 'د. ', 'د ', 'مهندس ', 'دكتور ']
    for p in prefixes:
        if name.startswith(p):
            name = name[len(p):]
    return name.strip()


def parse_smart_line(line: str) -> dict:
    """
    Parse a single smart-attendance line.

    Formats handled:
      • "خالد طارق"          → {name: "خالد طارق", workers_count: 1}
      • "6 عمال سامح"        → {name: "سامح",       workers_count: 6}
      • "2 أشرف"             → {name: "أشرف",        workers_count: 2}
      • "3 ع محمد"           → {name: "محمد",        workers_count: 3}
      • "2 workers Ali"      → {name: "Ali",         workers_count: 2}
      • "عمال خالد 3.5"      → {name: "خالد",        workers_count: 3.5}  (fractional, trailing count)
      • "م محمد"             → {name: "محمد",        workers_count: 1}  (old prefix style)

    The count can be a whole number or a fraction (e.g. "3.5" or "3,5"),
    and can appear either before or after the name. Arabic-Indic digits
    (٠-٩) are normalized to Western digits first. If no number is found,
    workers_count defaults to 1 (a single person).

    Returns dict with keys: name (str), workers_count (int | float)
    """
    line = line.strip()
    if not line:
        return None

    line = line.translate(_AR_DIGITS)

    workers_count = 1
    m = _COUNT_RE.search(line)
    if m:
        num_str = m.group(1).replace(',', '.')
        try:
            workers_count = float(num_str)
            if workers_count.is_integer():
                workers_count = int(workers_count)
        except ValueError:
            workers_count = 1
        else:
            # Remove just the matched number, wherever it sits in the line
            line = (line[:m.start()] + ' ' + line[m.end():]).strip()

    # Strip noise words (e.g. "عمال", "عامل")
    name = _NOISE_WORDS.sub('', line).strip()
    name = re.sub(r'\s+', ' ', name).strip()

    # Strip legacy name prefixes
    name = normalize_name(name)

    if not name:
        return None

    return {'name': name, 'workers_count': workers_count}


def parse_smart_attendance_text(text: str):
    """
    Parse the smart pasted attendance format.

    First line may optionally be a date (DD/MM/YYYY).
    Remaining lines are employee entries (with optional leading count).

    Returns:
        att_date  – date object (today if not found in text)
        entries   – list of {name, workers_count}
        errors    – list of error strings
    """
    lines = [l.strip() for l in text.strip().splitlines()]
    lines = [l for l in lines if l]

    if not lines:
        return None, [], ['النص فارغ']

    att_date = None
    start_idx = 0

    # Try to parse first line as a date
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y'):
        try:
            att_date = datetime.strptime(lines[0], fmt).date()
            start_idx = 1
            break
        except ValueError:
            continue

    # Default to today if no date found
    if att_date is None:
        att_date = date.today()

    entries = []
    for line in lines[start_idx:]:
        parsed = parse_smart_line(line)
        if parsed:
            entries.append(parsed)

    if not entries:
        return att_date, [], ['لم يتم العثور على أسماء صالحة في النص']

    return att_date, entries, []


def process_smart_attendance(text: str, confirm_updates: bool = False):
    """
    Parse smart attendance text and save to DB.

    Each entry's workers_count is stored on the Attendance record
    (falls back gracefully if column absent).

    Returns result dict compatible with the UI.
    """
    att_date, entries, errors = parse_smart_attendance_text(text)
    if errors:
        return {'success': False, 'errors': errors}

    db = get_db()
    try:
        current_project_id = get_current_project_id()
        employees = db.query(Employee).filter(
            Employee.status == 'Active',
            Employee.project_id == current_project_id,
        ).all()
        # Smart/tolerant Arabic name matching (diacritics, أ/إ/آ/ا,
        # "أبو"/"ابو", extra spaces — see services/name_matching.py).
        # Never picks randomly between multiple plausible matches; those
        # are routed to `unmatched` for a human to resolve, same as a
        # name that matches nothing at all.
        name_index = build_employee_name_index(employees)

        matched      = []
        unmatched    = []
        saved        = 0
        duplicates   = 0
        updated      = 0
        conflicts    = []
        seen_in_batch = set()   # employee_ids already queued for insert in THIS run

        for entry in entries:
            name          = entry['name']
            workers_count = entry['workers_count']

            emp, _match_status = match_employee_by_name(name, name_index=name_index)

            if emp:
                already_in_db = db.query(Attendance).filter(
                    Attendance.employee_id == emp.id,
                    Attendance.attendance_date == att_date,
                    Attendance.project_id == current_project_id,
                ).first()
                if already_in_db:
                    if confirm_updates:
                        already_in_db.status = 1
                        already_in_db.workers_count = workers_count
                        updated += 1
                    else:
                        conflicts.append({
                            'name': emp.name,
                            'old': {'status': already_in_db.status, 'workers_count': already_in_db.workers_count},
                            'new': {'status': 1, 'workers_count': workers_count},
                        })
                elif emp.id in seen_in_batch:
                    duplicates += 1
                else:
                    att = Attendance(
                        employee_id=emp.id,
                        attendance_date=att_date,
                        status=1,            # presence "credit" for payroll — always 1 per day, unaffected by count
                        workers_count=workers_count,  # real headcount for the matrix
                        project_id=current_project_id,
                    )
                    db.add(att)
                    seen_in_batch.add(emp.id)
                    saved += 1
                matched.append({'name': emp.name, 'workers_count': workers_count})
            else:
                unmatched.append({'name': name, 'workers_count': workers_count})

        if conflicts and not confirm_updates:
            db.rollback()
            return {
                'success': False, 'requires_confirmation': True,
                'conflicts': conflicts, 'date': att_date,
            }

        db.commit()
        clear_payroll_cache()
        return {
            'success':    True,
            'date':       att_date,
            'matched':    matched,
            'unmatched':  unmatched,
            'saved':      saved,
            'updated':    updated,
            'duplicates': duplicates,
            'entries':    entries,
        }
    except Exception as e:
        db.rollback()
        return {'success': False, 'errors': [str(e)]}
    finally:
        db.close()


# ── Legacy functions (unchanged) ─────────────────────────────────

def parse_attendance_text(text: str):
    """Parse attendance plain text. Returns (date, names_list, errors)."""
    lines = [l.strip() for l in text.strip().splitlines()]
    lines = [l for l in lines if l]
    if not lines:
        return None, [], ['النص فارغ']
    date_line = lines[0]
    att_date = None
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y'):
        try:
            att_date = datetime.strptime(date_line, fmt).date()
            break
        except ValueError:
            continue
    if att_date is None:
        return None, [], [f'تنسيق التاريخ غير صحيح: {date_line}']
    names = list(dict.fromkeys([normalize_name(l) for l in lines[1:] if l.strip()]))
    return att_date, names, []


def process_attendance(text: str, confirm_updates: bool = False):
    """Process attendance text and save to DB. Returns result dict."""
    att_date, names, errors = parse_attendance_text(text)
    if errors:
        return {'success': False, 'errors': errors}
    db = get_db()
    try:
        current_project_id = get_current_project_id()
        employees = db.query(Employee).filter(
            Employee.status == 'Active',
            Employee.project_id == current_project_id,
        ).all()
        # See process_smart_attendance() above for why this replaced the
        # old exact/substring-only matching.
        name_index = build_employee_name_index(employees)
        matched = []
        unmatched = []
        saved = 0
        duplicates = 0
        updated = 0
        conflicts = []
        seen_in_batch = set()   # employee_ids already queued for insert in THIS run
        for name in names:
            emp, _match_status = match_employee_by_name(name, name_index=name_index)
            if emp:
                already_in_db = db.query(Attendance).filter(
                    Attendance.employee_id == emp.id,
                    Attendance.attendance_date == att_date,
                    Attendance.project_id == current_project_id,
                ).first()
                if already_in_db:
                    if confirm_updates:
                        already_in_db.status = 1
                        already_in_db.workers_count = 1.0
                        updated += 1
                    else:
                        conflicts.append({
                            'name': emp.name,
                            'old': {'status': already_in_db.status, 'workers_count': already_in_db.workers_count},
                            'new': {'status': 1, 'workers_count': 1.0},
                        })
                elif emp.id in seen_in_batch:
                    duplicates += 1
                else:
                    att = Attendance(
                        employee_id=emp.id, attendance_date=att_date, status=1,
                        project_id=current_project_id,
                    )
                    db.add(att)
                    seen_in_batch.add(emp.id)
                    saved += 1
                matched.append(emp.name)
            else:
                unmatched.append(name)
        if conflicts and not confirm_updates:
            db.rollback()
            return {
                'success': False, 'requires_confirmation': True,
                'conflicts': conflicts, 'date': att_date,
            }

        db.commit()
        clear_payroll_cache()
        return {
            'success': True,
            'date': att_date,
            'matched': matched,
            'unmatched': unmatched,
            'saved': saved,
            'duplicates': duplicates,
            'updated': updated,
        }
    except Exception as e:
        db.rollback()
        return {'success': False, 'errors': [str(e)]}
    finally:
        db.close()


# ── Edit / Delete (single record, day, month) ─────────────────────
#
# All deletes below are scoped by Primary Key and/or (date/month + year)
# AND project_id — never by employee name alone, and never an
# unconditional DELETE. Every function opens its own short-lived
# session, commits inside a try block, and rolls back on any exception
# so the database is never left in a partial state.

def update_attendance_record(record_id: int, project_id: int, employee_id: int,
                              attendance_date, workers_count: float = 1.0,
                              status: int = 1) -> tuple[bool, str]:
    """
    Edit a single attendance record, identified by its Primary Key
    (`record_id`). `project_id` must match the record's stored
    project_id, or the update is refused — this stops one project's
    UI from ever touching another project's row, even if a record id
    were somehow mixed up.

    Also re-checks the (employee_id, attendance_date) uniqueness rule
    against any OTHER record, exactly like the existing Overtime edit
    flow, so an edit can't silently create a duplicate day for the
    same employee.

    Returns (success, message).
    """
    db = get_db()
    try:
        obj = db.query(Attendance).filter(
            Attendance.id == record_id,
            Attendance.project_id == project_id,
        ).first()
        if not obj:
            return False, "السجل غير موجود أو لا يخص هذا المشروع."

        dup = db.query(Attendance).filter(
            Attendance.employee_id == employee_id,
            Attendance.attendance_date == attendance_date,
            Attendance.id != record_id,
        ).first()
        if dup:
            return False, "يوجد بالفعل سجل حضور آخر لهذا الموظف بنفس التاريخ."

        obj.employee_id = employee_id
        obj.attendance_date = attendance_date
        obj.workers_count = workers_count
        obj.status = status
        db.commit()
        clear_payroll_cache()
        return True, "تم تحديث سجل الحضور بنجاح."
    except Exception as e:
        db.rollback()
        return False, f"خطأ أثناء التحديث: {e}"
    finally:
        db.close()


def mark_attendance_bulk_dates(employee_id: int, dates: list, project_id: int,
                                workers_count: float = 1.0, status: int = 1) -> dict:
    """
    Mark ONE employee present (or absent) on a set of specific, possibly
    non-consecutive, dates in a single call — the "pick the employee, tick
    the days he actually showed up, save once" backdated-attendance flow.

    Skips any date that already has an attendance row for this employee
    (the (employee_id, attendance_date) UniqueConstraint) rather than
    erroring out — those are reported back separately as `duplicate_dates`
    so the caller can show the user exactly which days were skipped and
    why, instead of failing the whole batch over one already-recorded day.

    `project_id` must match the employee's own project_id, or nothing is
    written — same cross-project safety rule as the rest of this module.

    Returns a dict:
        {
            'success': bool,
            'saved': int,                  # rows actually inserted
            'saved_dates': [date, ...],
            'duplicate_dates': [date, ...],# already had a record, skipped
            'error': str | None,
        }
    """
    if not dates:
        return {'success': False, 'saved': 0, 'saved_dates': [],
                'duplicate_dates': [], 'error': "لم يتم اختيار أي يوم."}

    db = get_db()
    try:
        emp = db.query(Employee).filter(
            Employee.id == employee_id, Employee.project_id == project_id
        ).first()
        if not emp:
            return {'success': False, 'saved': 0, 'saved_dates': [],
                    'duplicate_dates': [], 'error': "الموظف غير موجود أو لا يخص هذا المشروع."}

        # Unique-ify and sort input dates defensively (multiselect widgets
        # can't produce duplicates, but this stays correct even if called
        # from elsewhere with a raw list).
        unique_dates = sorted(set(dates))

        existing = {
            r.attendance_date
            for r in db.query(Attendance.attendance_date).filter(
                Attendance.employee_id == employee_id,
                Attendance.attendance_date.in_(unique_dates),
            ).all()
        }

        saved_dates = []
        for d in unique_dates:
            if d in existing:
                continue
            db.add(Attendance(
                employee_id=employee_id,
                attendance_date=d,
                status=status,
                workers_count=workers_count,
                project_id=project_id,
            ))
            saved_dates.append(d)

        db.commit()
        if saved_dates:
            clear_payroll_cache()

        duplicate_dates = [d for d in unique_dates if d in existing]
        return {
            'success': True,
            'saved': len(saved_dates),
            'saved_dates': saved_dates,
            'duplicate_dates': duplicate_dates,
            'error': None,
        }
    except Exception as e:
        db.rollback()
        return {'success': False, 'saved': 0, 'saved_dates': [],
                'duplicate_dates': [], 'error': f"خطأ أثناء الحفظ: {e}"}
    finally:
        db.close()


def delete_attendance_record(record_id: int, project_id: int) -> tuple[bool, str]:
    """
    Delete ONE attendance record by its Primary Key.

    `project_id` must match the record's own project_id, or nothing is
    deleted — this is the safety net against cross-project deletion
    (see module docstring above). Never deletes by employee name, date
    alone, or any other non-unique value.
    """
    db = get_db()
    try:
        obj = db.query(Attendance).filter(
            Attendance.id == record_id,
            Attendance.project_id == project_id,
        ).first()
        if not obj:
            return False, "السجل غير موجود أو لا يخص هذا المشروع."
        db.delete(obj)
        db.commit()
        clear_payroll_cache()
        return True, "تم حذف السجل بنجاح."
    except Exception as e:
        db.rollback()
        return False, f"خطأ أثناء الحذف: {e}"
    finally:
        db.close()


def count_attendance_for_day(target_date, project_id: int) -> int:
    """Count-only query (no rows loaded) — used to show the user how many
    records a 'delete day' action would affect, before any confirmation."""
    db = get_db()
    try:
        return db.query(Attendance).filter(
            Attendance.attendance_date == target_date,
            Attendance.project_id == project_id,
        ).count()
    finally:
        db.close()


def delete_attendance_for_day(target_date, project_id: int) -> tuple[int, str]:
    """
    Delete every attendance record for one specific date, scoped to
    ONE project. Uses a single database-side DELETE (via the ORM query,
    `synchronize_session=False`) instead of loading every row into
    memory first — safe for a day that could have hundreds of rows.

    Both `attendance_date` AND `project_id` are always in the WHERE
    clause together, so this can never spill into another project's
    data for the same date. Never called without an explicit prior
    confirmation from the UI layer.

    Returns (deleted_count, error_message_or_None_as_empty_string).
    """
    db = get_db()
    try:
        deleted_count = db.query(Attendance).filter(
            Attendance.attendance_date == target_date,
            Attendance.project_id == project_id,
        ).delete(synchronize_session=False)
        db.commit()
        clear_payroll_cache()
        return deleted_count, ""
    except Exception as e:
        db.rollback()
        return 0, str(e)
    finally:
        db.close()


def count_attendance_for_month(year: int, month: int, project_id: int) -> int:
    """Count-only query for a whole month, scoped to one project."""
    import calendar
    db = get_db()
    try:
        days_in_month = calendar.monthrange(year, month)[1]
        start_date = date(year, month, 1)
        end_date = date(year, month, days_in_month)
        return db.query(Attendance).filter(
            Attendance.attendance_date >= start_date,
            Attendance.attendance_date <= end_date,
            Attendance.project_id == project_id,
        ).count()
    finally:
        db.close()


def delete_attendance_for_month(year: int, month: int, project_id: int) -> tuple[int, str]:
    """
    Delete every attendance record for one calendar month, scoped to
    ONE project. Same database-side bulk-delete approach as
    delete_attendance_for_day() — a month can hold thousands of rows,
    so nothing is loaded into Python memory first.

    date range AND project_id are always combined in the WHERE clause.
    Never called without an explicit prior confirmation from the UI.

    Returns (deleted_count, error_message_or_empty_string).
    """
    import calendar
    db = get_db()
    try:
        days_in_month = calendar.monthrange(year, month)[1]
        start_date = date(year, month, 1)
        end_date = date(year, month, days_in_month)
        deleted_count = db.query(Attendance).filter(
            Attendance.attendance_date >= start_date,
            Attendance.attendance_date <= end_date,
            Attendance.project_id == project_id,
        ).delete(synchronize_session=False)
        db.commit()
        clear_payroll_cache()
        return deleted_count, ""
    except Exception as e:
        db.rollback()
        return 0, str(e)
    finally:
        db.close()


def get_attendance_matrix(month: int, year: int, department: str = None, employee_id: int = None,
                           project_id: int = None) -> pd.DataFrame:
    """Generate attendance matrix for a given month/year, scoped to a
    project (defaults to the currently-selected one)."""
    import calendar
    db = get_db()
    try:
        if project_id is None:
            project_id = get_current_project_id()
        days_in_month = calendar.monthrange(year, month)[1]
        query = db.query(Employee).filter(Employee.project_id == project_id)
        if department:
            query = query.filter(Employee.department == department)
        if employee_id:
            query = query.filter(Employee.id == employee_id)
        employees = query.filter(Employee.status == 'Active').all()
        if not employees:
            return pd.DataFrame()
        emp_ids = [e.id for e in employees]
        from sqlalchemy import and_
        start_date = date(year, month, 1)
        end_date = date(year, month, days_in_month)
        records = db.query(Attendance).filter(
            Attendance.employee_id.in_(emp_ids),
            Attendance.attendance_date >= start_date,
            Attendance.attendance_date <= end_date,
            Attendance.project_id == project_id,
        ).all()
        # Matrix cells show the real headcount for PRESENT employees only.
        # An absence row can still carry the database default workers_count
        # (1.0), so using that value unconditionally would turn an absence
        # into attendance in both the matrix and the exported report.
        att_set = {
            (r.employee_id, r.attendance_date.day):
                ((r.workers_count if r.workers_count is not None else 1.0)
                 if r.status == 1 else 0)
            for r in records
        }
        rows = []
        for emp in employees:
            row = {'كود الموظف': emp.code, 'اسم الموظف': emp.name}
            for d in range(1, days_in_month + 1):
                row[str(d)] = att_set.get((emp.id, d), 0)
            row['إجمالي الحضور'] = sum(att_set.get((emp.id, d), 0) for d in range(1, days_in_month + 1))
            rows.append(row)
        return pd.DataFrame(rows)
    finally:
        db.close()
