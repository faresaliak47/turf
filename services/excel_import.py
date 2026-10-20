"""
Excel Import Service
Restores HR data from previously exported Excel reports.
Supports Merge and Replace modes with duplicate prevention.
"""
import io
from datetime import date, datetime
from typing import Dict, List, Tuple, Any
import pandas as pd
from database.db import get_db
from database.models import Employee, Attendance, Overtime, Advance, PayrollCache
from services.projects import get_current_project_id
from services.payroll_service import clear_payroll_cache


# ── Column mappings: Excel header → model field ──────────────────────────────

EMP_COLUMNS = {
    'كود':             'code',
    'الاسم':           'name',
    'المسمى الوظيفي': 'job_title',
    'القسم':           'department',
    'الراتب':          'salary',
    'المعدل اليومي':  'daily_rate',
    'الهاتف':         'phone',
    'الرقم القومي':   'national_id',
    'المنطقة':        'area',
    'تاريخ التعيين':  'hire_date',
    'الحالة':         'status',
}

ATT_COLUMNS = {
    'كود الموظف':  'employee_code',
    'اسم الموظف': 'employee_name',
    'التاريخ':     'attendance_date',
    'الحالة':      'status_label',
    'عدد الأفراد': 'workers_count',
}

OT_COLUMNS = {
    'كود الموظف':  'employee_code',
    'اسم الموظف': 'employee_name',
    'التاريخ':     'date',
    'الساعات':     'hours',
    'معدل الساعة': 'rate_per_hour',
    'الإجمالي':   'amount',
    'ملاحظات':    'notes',
}

ADV_COLUMNS = {
    'كود الموظف':  'employee_code',
    'اسم الموظف': 'employee_name',
    'التاريخ':     'date',
    'المبلغ':      'amount',
    'ملاحظات':    'notes',
}

# Sheet names as written by excel_export.py
SHEET_EMPLOYEES  = 'الموظفون'
SHEET_ATTENDANCE = 'سجلات الحضور'
SHEET_OVERTIME   = 'الأوفر تايم'
SHEET_ADVANCES   = 'السلف'
SHEET_PAYROLL    = 'مسير الرواتب'
SHEET_MATRIX     = 'مصفوفة الحضور'

IMPORTABLE_SHEETS = [SHEET_EMPLOYEES, SHEET_ATTENDANCE, SHEET_OVERTIME, SHEET_ADVANCES]


# ── Validation ────────────────────────────────────────────────────────────────

def validate_file(file_bytes: bytes) -> Tuple[bool, str, Dict[str, pd.DataFrame]]:
    """
    Read and validate an uploaded Excel file.
    Returns (is_valid, message, sheet_dict).
    """
    try:
        xl = pd.ExcelFile(io.BytesIO(file_bytes))
    except Exception as e:
        return False, f"لا يمكن قراءة الملف: {e}", {}

    found_sheets = set(xl.sheet_names)
    importable   = [s for s in IMPORTABLE_SHEETS if s in found_sheets]

    if not importable:
        return (
            False,
            "الملف لا يحتوي على أي أوراق يمكن استيرادها. "
            "تأكد أن الملف تم تصديره من النظام.",
            {},
        )

    sheets: Dict[str, pd.DataFrame] = {}
    for sheet in importable:
        try:
            df = xl.parse(sheet)
            df.columns = [str(c).strip() for c in df.columns]
            sheets[sheet] = df
        except Exception as e:
            return False, f"خطأ في قراءة ورقة '{sheet}': {e}", {}

    # Validate Employees sheet columns
    if SHEET_EMPLOYEES in sheets:
        required = {'كود', 'الاسم'}
        missing  = required - set(sheets[SHEET_EMPLOYEES].columns)
        if missing:
            return False, f"ورقة الموظفين تفتقر لأعمدة: {missing}", {}

    return True, f"تم التحقق — {len(importable)} ورقة صالحة للاستيراد", sheets


# ── Preview ────────────────────────────────────────────────────────────────────

def build_preview(sheets: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    """
    Return summary counts and first rows for preview UI.
    """
    preview = {}
    for name, df in sheets.items():
        # Drop all-NaN rows
        df_clean = df.dropna(how='all')
        preview[name] = {
            'count': len(df_clean),
            'sample': df_clean.head(5),
            'columns': list(df_clean.columns),
        }
    return preview


# ── Import Core ───────────────────────────────────────────────────────────────

def import_report(
    sheets: Dict[str, pd.DataFrame],
    mode: str = 'merge',       # 'merge' | 'replace'
    project_id: int = None,
) -> Dict[str, Any]:
    """
    Import data from parsed sheets into the database, scoped to a project
    (defaults to the currently-selected one).
    mode='merge'   — skip existing records (no overwrite)
    mode='replace' — truncate this project's rows in the relevant tables
                     first, then insert all (never touches other projects'
                     data)
    Returns a results dict with counts and errors per sheet.
    """
    if project_id is None:
        project_id = get_current_project_id()

    results = {
        'employees':  {'inserted': 0, 'updated': 0, 'skipped': 0, 'errors': []},
        'attendance': {'inserted': 0, 'updated': 0, 'skipped': 0, 'errors': []},
        'overtime':   {'inserted': 0, 'updated': 0, 'skipped': 0, 'errors': []},
        'advances':   {'inserted': 0, 'updated': 0, 'skipped': 0, 'errors': []},
    }

    db = get_db()
    try:
        # ── Replace mode: clear THIS PROJECT's rows before inserting ──────
        # Scoped to project_id so replacing one project's data never
        # touches another project's employees/attendance/overtime/advances.
        if mode == 'replace':
            if SHEET_ADVANCES   in sheets: db.query(Advance).filter(Advance.project_id == project_id).delete()
            if SHEET_OVERTIME   in sheets: db.query(Overtime).filter(Overtime.project_id == project_id).delete()
            if SHEET_ATTENDANCE in sheets: db.query(Attendance).filter(Attendance.project_id == project_id).delete()
            if SHEET_EMPLOYEES  in sheets: db.query(Employee).filter(Employee.project_id == project_id).delete()
            db.query(PayrollCache).filter(PayrollCache.project_id == project_id).delete()
            db.commit()
            clear_payroll_cache()

        # ── Step 1: Employees ─────────────────────────────────────────────
        if SHEET_EMPLOYEES in sheets:
            _import_employees(db, sheets[SHEET_EMPLOYEES], mode, results['employees'], project_id)

        # Build code→id map for subsequent sheets (this project's employees only)
        code_to_id = {e.code: e.id for e in db.query(Employee).filter(Employee.project_id == project_id).all()}

        # ── Step 2: Attendance ────────────────────────────────────────────
        if SHEET_ATTENDANCE in sheets:
            _import_attendance(db, sheets[SHEET_ATTENDANCE], code_to_id, mode, results['attendance'], project_id)

        # ── Step 3: Overtime ──────────────────────────────────────────────
        if SHEET_OVERTIME in sheets:
            _import_overtime(db, sheets[SHEET_OVERTIME], code_to_id, mode, results['overtime'], project_id)

        # ── Step 4: Advances ──────────────────────────────────────────────
        if SHEET_ADVANCES in sheets:
            _import_advances(db, sheets[SHEET_ADVANCES], code_to_id, mode, results['advances'], project_id)

        db.commit()
        clear_payroll_cache()

    except Exception as e:
        db.rollback()
        raise RuntimeError(f"خطأ فادح أثناء الاستيراد: {e}") from e
    finally:
        db.close()

    return results


# ── Per-sheet helpers ─────────────────────────────────────────────────────────

def _safe_str(val, default='') -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    return str(val).strip()


def _safe_float(val, default=0.0) -> float:
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return default
        return float(val)
    except Exception:
        return default  # non-numeric value — return default silently


def _parse_date(val) -> date | None:
    if val is None:
        return None
    # Handle pandas NaT explicitly
    if type(val).__name__ == 'NaTType':
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    if isinstance(val, (date, datetime)):
        return val.date() if isinstance(val, datetime) else val
    try:
        s = str(val).strip()
        if not s or s.lower() in ('none', 'nat', 'nan', ''):
            return None
        return pd.to_datetime(s).date()
    except Exception:
        return None  # unparseable date — return None silently


def _import_employees(db, df: pd.DataFrame, mode: str, res: dict, project_id: int):
    """
    Import employees one row at a time, assigned to `project_id`.

    Each row runs inside its own SAVEPOINT (db.begin_nested()) instead of
    just a bare try/except. This matters because the surrounding
    import_report() only calls db.commit() once, at the very end, after
    all four sheets are processed — with autoflush=False, nothing is
    actually sent to the database until that single commit. A bare
    try/except around db.add(...) can't catch a problem that only shows
    up at flush/commit time (e.g. a UNIQUE/NOT NULL violation), so one
    bad employee row would fail the *one* final commit and roll back
    every employee, attendance, overtime, and advance row from the
    entire import — not just the bad one.

    Wrapping each row in begin_nested() gives it its own SAVEPOINT: on
    success the row's insert/update is flushed and kept; on failure only
    that row's SAVEPOINT is rolled back (and the failed row is the only
    thing un-done), while every other row — already-processed or
    still-to-come — is unaffected and the import keeps going.
    """
    df = df.dropna(subset=['كود', 'الاسم'], how='any')
    for _, row in df.iterrows():
        code = _safe_str(row.get('كود'))
        name = _safe_str(row.get('الاسم'))
        if not code or not name:
            continue
        try:
            with db.begin_nested():
                # Employee codes are unique within a project. The same code
                # may legitimately occur in a different project.
                existing = db.query(Employee).filter(
                    Employee.code == code,
                    Employee.project_id == project_id,
                ).first()
                if existing:
                    if mode == 'merge':
                        res['skipped'] += 1
                    else:  # replace — already cleared, but just in case
                        _fill_employee(existing, row)
                        existing.project_id = project_id
                        res['updated'] += 1
                else:
                    emp = Employee(code=code, name=name, project_id=project_id)
                    _fill_employee(emp, row)
                    db.add(emp)
                    res['inserted'] += 1
        except Exception as e:
            res['errors'].append(f"موظف {code}: {e}")


def _fill_employee(emp: Employee, row):
    emp.name      = _safe_str(row.get('الاسم'), emp.name)
    emp.job_title = _safe_str(row.get('المسمى الوظيفي'))
    emp.department= _safe_str(row.get('القسم'))
    emp.salary    = _safe_float(row.get('الراتب'))
    emp.daily_rate= _safe_float(row.get('المعدل اليومي'))
    emp.phone     = _safe_str(row.get('الهاتف'))
    emp.national_id = _safe_str(row.get('الرقم القومي'))
    emp.area      = _safe_str(row.get('المنطقة'))
    emp.status    = _safe_str(row.get('الحالة'), 'Active')
    hire_val = row.get('تاريخ التعيين')
    # Explicitly handle NaT / NaN before passing to _parse_date
    if hire_val is None or (hasattr(hire_val, '__class__') and type(hire_val).__name__ == 'NaTType'):
        emp.hire_date = None
    elif isinstance(hire_val, float) and pd.isna(hire_val):
        emp.hire_date = None
    else:
        hire = _parse_date(hire_val)
        emp.hire_date = hire  # None if parse fails, valid date otherwise


def _import_attendance(db, df: pd.DataFrame, code_to_id: dict, mode: str, res: dict, project_id: int):
    """
    Import attendance rows.

    Each row runs inside its own SAVEPOINT (db.begin_nested()), exactly
    like _import_employees above — same reason: with autoflush=False, a
    plain db.add() inside a bare try/except isn't sent to the database
    until the single final db.commit() in import_report(), so a
    UNIQUE-constraint violation (employee_id + attendance_date) can't be
    caught per-row and would instead fail the entire import.

    This also fixes a duplicate-handling gap: exiting a `begin_nested()`
    block flushes that row to the database connection (still inside the
    outer transaction), so the very next row's "does this already
    exist?" query can see it. Without this, two duplicate rows for the
    same employee+date *within the same uploaded file* were invisible
    to each other (autoflush=False) and only collided at the final
    commit, aborting the whole import instead of being skipped/updated
    like any other duplicate.
    """
    df = df.dropna(subset=['كود الموظف', 'التاريخ'], how='any')
    for _, row in df.iterrows():
        code     = _safe_str(row.get('كود الموظف'))
        emp_id   = code_to_id.get(code)
        att_date = _parse_date(row.get('التاريخ'))
        if not emp_id or not att_date:
            res['skipped'] += 1
            continue
        try:
            with db.begin_nested():
                status_label = _safe_str(row.get('الحالة'), 'حاضر')
                status = 1 if status_label == 'حاضر' else 0
                # Real headcount (e.g. "5 عمال أشرف" -> 5). Falls back to 1
                # for older exports that don't have this column yet, or
                # blank cells.
                workers_count = _safe_float(row.get('عدد الأفراد'), 1.0)
                existing = (
                    db.query(Attendance)
                    .filter(Attendance.employee_id == emp_id,
                            Attendance.attendance_date == att_date)
                    .first()
                )
                if existing:
                    if mode == 'merge':
                        res['skipped'] += 1
                    else:
                        existing.status = status
                        existing.workers_count = workers_count
                        existing.project_id = project_id
                        res['updated'] += 1
                else:
                    db.add(Attendance(
                        employee_id=emp_id, attendance_date=att_date,
                        status=status, workers_count=workers_count,
                        project_id=project_id,
                    ))
                    res['inserted'] += 1
        except Exception as e:
            res['errors'].append(f"حضور {code} {att_date}: {e}")


def _import_overtime(db, df: pd.DataFrame, code_to_id: dict, mode: str, res: dict, project_id: int):
    """
    Import overtime rows.

    Overtime intentionally allows more than one entry per employee per
    day (e.g. two separate sessions on the same date), so — unlike
    attendance/advances — there's no "already exists" check here. Every
    row from the sheet is inserted as its own new record, in both merge
    and replace mode.

    Still wrapped in its own SAVEPOINT (db.begin_nested()), same as
    employees/attendance above, so one row with a bad value (e.g. a
    non-numeric cell that slips past _safe_float, or any other
    per-row failure) is skipped and reported without failing the
    entire import.
    """
    df = df.dropna(subset=['كود الموظف', 'التاريخ'], how='any')
    for _, row in df.iterrows():
        code   = _safe_str(row.get('كود الموظف'))
        emp_id = code_to_id.get(code)
        ot_date = _parse_date(row.get('التاريخ'))
        if not emp_id or not ot_date:
            res['skipped'] += 1
            continue
        try:
            with db.begin_nested():
                hours = _safe_float(row.get('الساعات'))
                rate  = _safe_float(row.get('معدل الساعة'))
                amount= _safe_float(row.get('الإجمالي'), hours * rate)
                notes = _safe_str(row.get('ملاحظات'))
                # One employee has one overtime entry per day in the UI.
                # In merge mode, an exported file may be imported again;
                # skip the existing day instead of silently doubling hours.
                existing = db.query(Overtime).filter(
                    Overtime.employee_id == emp_id,
                    Overtime.date == ot_date,
                    Overtime.project_id == project_id,
                ).first()
                if existing:
                    res['skipped'] += 1
                    continue
                db.add(Overtime(
                    employee_id=emp_id, date=ot_date,
                    hours=hours, rate_per_hour=rate, amount=amount, notes=notes,
                    project_id=project_id,
                ))
                res['inserted'] += 1
        except Exception as e:
            res['errors'].append(f"أوفر تايم {code} {ot_date}: {e}")


def _import_advances(db, df: pd.DataFrame, code_to_id: dict, mode: str, res: dict, project_id: int):
    """
    Import advance rows. Same per-row SAVEPOINT treatment as
    _import_attendance above, and for the same reason: it lets the
    "already exists" check (employee_id + date + amount) see rows
    added earlier in the same uploaded file, instead of only seeing
    rows already in the database before the import started.
    """
    df = df.dropna(subset=['كود الموظف', 'التاريخ'], how='any')
    for _, row in df.iterrows():
        code   = _safe_str(row.get('كود الموظف'))
        emp_id = code_to_id.get(code)
        adv_date = _parse_date(row.get('التاريخ'))
        if not emp_id or not adv_date:
            res['skipped'] += 1
            continue
        try:
            with db.begin_nested():
                amount = _safe_float(row.get('المبلغ'))
                notes  = _safe_str(row.get('ملاحظات'))
                existing = (
                    db.query(Advance)
                    .filter(Advance.employee_id == emp_id,
                            Advance.date == adv_date,
                            Advance.amount == amount)
                    .first()
                )
                if existing:
                    if mode == 'merge':
                        res['skipped'] += 1
                    else:
                        existing.notes = notes
                        existing.project_id = project_id
                        res['updated'] += 1
                else:
                    db.add(Advance(
                        employee_id=emp_id, date=adv_date, amount=amount, notes=notes,
                        project_id=project_id,
                    ))
                    res['inserted'] += 1
        except Exception as e:
            res['errors'].append(f"سلفة {code} {adv_date}: {e}")
