import logging
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from database.models import Base
from database.paths import get_db_path

# Path resolution (dev vs. packaged .exe, Program-Files-write-permission
# safety, legacy-location backward compatibility) lives in database/paths.py
# — see that module's docstring for the full rationale.
DB_PATH = get_db_path()
# get_db_path() already prepares this folder. Keep a defensive check here,
# before SQLAlchemy/SQLite opens the file, so a missing parent never becomes
# an opaque "unable to open database file" startup failure.
os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
_log = logging.getLogger(__name__)

# expire_on_commit=False prevents stale-data issues after commit/rerun cycles
engine = create_engine(
    f'sqlite:///{DB_PATH}',
    echo=False,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,   # ← FIX: prevents stale reads after commit
)


# SQLite ships with foreign-key *enforcement* OFF by default for every
# connection, even when the schema declares ForeignKey columns (this is a
# SQLite quirk, not a SQLAlchemy one). Turning it on here means the
# employees.id ForeignKey on Attendance/Overtime/Advance/PayrollCache
# actually protects data integrity (e.g. blocks inserting a row with an
# employee_id that doesn't exist) on every NEW database created by
# create_all(). It's a safe no-op for already-existing databases whose
# tables were created before the FK existed — SQLite can't retroactively
# enforce a constraint that was never part of a table's schema (see the
# note in _migrate_add_missing_columns below).
@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


DEFAULT_PROJECT_NAME = "المشروع الافتراضي"


def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        _ensure_default_project()
        _migrate_add_missing_columns()
    except Exception:
        _log.exception("Database startup failed (path=%s)", DB_PATH)
        raise


def _ensure_default_project():
    """
    Guarantee at least one Project row exists before anything else runs.
    This must happen BEFORE the project_id column migrations below, since
    their backfill statements reference this row by name to assign every
    pre-existing employee/attendance/overtime/advance/expense/etc. row to
    it. Safe to call on every startup — no-ops once a project exists.
    """
    with engine.connect() as conn:
        row = conn.exec_driver_sql("SELECT COUNT(*) FROM projects").fetchone()
        if row and row[0] == 0:
            conn.exec_driver_sql(
                "INSERT INTO projects (name, is_active) VALUES (?, 1)",
                (DEFAULT_PROJECT_NAME,),
            )
            conn.commit()


# ── Lightweight migrations for existing SQLite DBs ───────────────────────
#
# Base.metadata.create_all() only creates tables that don't exist yet —
# it never alters a table that's already there. So whenever a column is
# added to a model after the app has already shipped, it needs an entry
# here too, or anyone upgrading from an older database silently keeps the
# old schema and the app breaks at the first query that touches the new
# column.
#
# Each entry is self-contained and independent, so adding a future
# column migration is just "append a dict to this list" — no need to
# touch the loop in _migrate_add_missing_columns itself.
#
# IMPORTANT — what this mechanism can and can't do:
#   - It CAN safely add a new nullable/defaulted column to an existing
#     table (SQLite supports `ALTER TABLE ... ADD COLUMN` for that).
#   - It CANNOT add or change a constraint (NOT NULL without a default,
#     UNIQUE, FOREIGN KEY, etc.) on a table that already exists — SQLite
#     has no `ALTER TABLE ... ADD CONSTRAINT`; that requires rebuilding
#     the table (create new table → copy data → drop old → rename), or a
#     real migration tool such as Alembic. The ForeignKey constraints
#     added to models.py, for example, will only be physically present
#     on brand-new databases; existing data/hr.db files won't gain them
#     retroactively. If/when more constraint-level changes are needed,
#     prefer adopting Alembic rather than growing ad-hoc table-rebuild
#     code here.
_COLUMN_MIGRATIONS = [
    {
        'table':    'attendance',
        'column':   'workers_count',
        'ddl':      "ALTER TABLE attendance ADD COLUMN workers_count FLOAT DEFAULT 1.0",
        'backfill': "UPDATE attendance SET workers_count = 1.0 WHERE workers_count IS NULL",
    },
    # ── Multi-project support ──────────────────────────────────────────
    # Every operational table gets a nullable project_id column. Backfill
    # assigns every pre-existing row (created before projects existed) to
    # the auto-created default project (see _ensure_default_project above,
    # which always runs first) — this is what "migrate existing data to a
    # default project automatically" means in practice.
    {
        'table':    'employees',
        'column':   'project_id',
        'ddl':      "ALTER TABLE employees ADD COLUMN project_id INTEGER REFERENCES projects(id)",
        'backfill': f"UPDATE employees SET project_id = (SELECT id FROM projects WHERE name = '{DEFAULT_PROJECT_NAME}' LIMIT 1) WHERE project_id IS NULL",
    },
    {
        'table':    'attendance',
        'column':   'project_id',
        'ddl':      "ALTER TABLE attendance ADD COLUMN project_id INTEGER REFERENCES projects(id)",
        'backfill': f"UPDATE attendance SET project_id = (SELECT id FROM projects WHERE name = '{DEFAULT_PROJECT_NAME}' LIMIT 1) WHERE project_id IS NULL",
    },
    {
        'table':    'overtime',
        'column':   'project_id',
        'ddl':      "ALTER TABLE overtime ADD COLUMN project_id INTEGER REFERENCES projects(id)",
        'backfill': f"UPDATE overtime SET project_id = (SELECT id FROM projects WHERE name = '{DEFAULT_PROJECT_NAME}' LIMIT 1) WHERE project_id IS NULL",
    },
    {
        'table':    'advances',
        'column':   'project_id',
        'ddl':      "ALTER TABLE advances ADD COLUMN project_id INTEGER REFERENCES projects(id)",
        'backfill': f"UPDATE advances SET project_id = (SELECT id FROM projects WHERE name = '{DEFAULT_PROJECT_NAME}' LIMIT 1) WHERE project_id IS NULL",
    },
    {
        'table':    'payroll_cache',
        'column':   'project_id',
        'ddl':      "ALTER TABLE payroll_cache ADD COLUMN project_id INTEGER REFERENCES projects(id)",
        'backfill': f"UPDATE payroll_cache SET project_id = (SELECT id FROM projects WHERE name = '{DEFAULT_PROJECT_NAME}' LIMIT 1) WHERE project_id IS NULL",
    },
    {
        'table':    'expenses',
        'column':   'project_id',
        'ddl':      "ALTER TABLE expenses ADD COLUMN project_id INTEGER REFERENCES projects(id)",
        'backfill': f"UPDATE expenses SET project_id = (SELECT id FROM projects WHERE name = '{DEFAULT_PROJECT_NAME}' LIMIT 1) WHERE project_id IS NULL",
    },
    {
        'table':    'received_funds',
        'column':   'project_id',
        'ddl':      "ALTER TABLE received_funds ADD COLUMN project_id INTEGER REFERENCES projects(id)",
        'backfill': f"UPDATE received_funds SET project_id = (SELECT id FROM projects WHERE name = '{DEFAULT_PROJECT_NAME}' LIMIT 1) WHERE project_id IS NULL",
    },
    {
        'table':    'users',
        'column':   'last_project_id',
        'ddl':      "ALTER TABLE users ADD COLUMN last_project_id INTEGER REFERENCES projects(id)",
        'backfill': None,
    },
    # ── Discounts feature ───────────────────────────────────────────────
    # payroll_cache gained a `discounts` column alongside the pre-existing
    # `advances` one — the `discounts` table itself is brand new, so it
    # needs no migration entry (Base.metadata.create_all() already creates
    # any table that doesn't exist yet, see init_db() above).
    {
        'table':    'payroll_cache',
        'column':   'discounts',
        'ddl':      "ALTER TABLE payroll_cache ADD COLUMN discounts FLOAT DEFAULT 0.0",
        'backfill': "UPDATE payroll_cache SET discounts = 0.0 WHERE discounts IS NULL",
    },
    {
        'table':    'check_records',
        'column':   'settlement_number',
        'ddl':      "ALTER TABLE check_records ADD COLUMN settlement_number VARCHAR(100)",
        'backfill': None,
    },
    # Add future "new column on an existing table" migrations here, e.g.:
    # {
    #     'table':    'employees',
    #     'column':   'email',
    #     'ddl':      "ALTER TABLE employees ADD COLUMN email VARCHAR(120)",
    #     'backfill': None,
    # },
]

# Indexes that may be missing from databases created before they were
# added to models.py. Unlike column additions, `CREATE INDEX IF NOT
# EXISTS` is always safe to run unconditionally on every startup — no
# existence check needed beforehand, and no harm done on a brand-new DB
# where create_all() already created the very same index (names below
# match SQLAlchemy's default `ix_<table>_<column>` convention so no
# duplicate index is created).
_INDEX_MIGRATIONS = [
    "CREATE INDEX IF NOT EXISTS ix_attendance_employee_id ON attendance (employee_id)",
    "CREATE INDEX IF NOT EXISTS ix_attendance_attendance_date ON attendance (attendance_date)",
    "CREATE INDEX IF NOT EXISTS ix_attendance_status ON attendance (status)",
    "CREATE INDEX IF NOT EXISTS ix_attendance_date_status ON attendance (attendance_date, status)",
    "CREATE INDEX IF NOT EXISTS ix_overtime_employee_id ON overtime (employee_id)",
    "CREATE INDEX IF NOT EXISTS ix_overtime_date ON overtime (date)",
    "CREATE INDEX IF NOT EXISTS ix_advances_employee_id ON advances (employee_id)",
    "CREATE INDEX IF NOT EXISTS ix_advances_date ON advances (date)",
    "CREATE INDEX IF NOT EXISTS ix_discounts_employee_id ON discounts (employee_id)",
    "CREATE INDEX IF NOT EXISTS ix_discounts_date ON discounts (date)",
    "CREATE INDEX IF NOT EXISTS ix_discounts_project_id ON discounts (project_id)",
    "CREATE INDEX IF NOT EXISTS ix_payroll_cache_employee_id ON payroll_cache (employee_id)",
    "CREATE INDEX IF NOT EXISTS ix_expenses_date ON expenses (date)",
    "CREATE INDEX IF NOT EXISTS ix_expenses_category ON expenses (category)",
    "CREATE INDEX IF NOT EXISTS ix_received_funds_date ON received_funds (date)",
    # ── Multi-project support ────────────────────────────────────────
    "CREATE INDEX IF NOT EXISTS ix_employees_project_id ON employees (project_id)",
    "CREATE INDEX IF NOT EXISTS ix_attendance_project_id ON attendance (project_id)",
    "CREATE INDEX IF NOT EXISTS ix_overtime_project_id ON overtime (project_id)",
    "CREATE INDEX IF NOT EXISTS ix_advances_project_id ON advances (project_id)",
    "CREATE INDEX IF NOT EXISTS ix_payroll_cache_project_id ON payroll_cache (project_id)",
    "CREATE INDEX IF NOT EXISTS ix_expenses_project_id ON expenses (project_id)",
    "CREATE INDEX IF NOT EXISTS ix_received_funds_project_id ON received_funds (project_id)",
]


def _migrate_add_missing_columns():
    """
    Run all lightweight migrations. Safe to call on every app startup —
    every step below is a no-op once already applied.
    """
    with engine.connect() as conn:
        # 1) New columns on existing tables — each needs an explicit
        #    existence check since SQLite has no "ADD COLUMN IF NOT
        #    EXISTS".
        for m in _COLUMN_MIGRATIONS:
            cols = [row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({m['table']})").fetchall()]
            if not cols:
                continue  # table doesn't exist yet — create_all() already built it with the column included
            if m['column'] in cols:
                continue  # migration already applied previously
            conn.exec_driver_sql(m['ddl'])
            if m.get('backfill'):
                conn.exec_driver_sql(m['backfill'])
            conn.commit()

        # 2) Constraints. SQLite cannot alter a UNIQUE constraint in place,
        # so installations created before project scoping need a one-time
        # table rebuild. IDs are copied unchanged, preserving every related
        # attendance, overtime, advance, and payroll record.
        _rebuild_legacy_project_constraints(conn)

        # 3) Indexes — safe to (re)run unconditionally every startup.
        for stmt in _INDEX_MIGRATIONS:
            conn.exec_driver_sql(stmt)
        conn.commit()


def _unique_indexes(conn, table: str) -> list[tuple[str, ...]]:
    """Return the column lists of a table's unique indexes."""
    indexes = []
    for row in conn.exec_driver_sql(f"PRAGMA index_list({table})").fetchall():
        # PRAGMA index_list: sequence, name, unique, origin, partial
        if row[2]:
            columns = conn.exec_driver_sql(f"PRAGMA index_info({row[1]})").fetchall()
            indexes.append(tuple(column[2] for column in columns))
    return indexes


def _rebuild_legacy_project_constraints(conn):
    """Upgrade old global uniqueness rules to project-scoped uniqueness.

    Earlier versions made employee codes and attendance dates globally unique.
    That prevented an otherwise independent project from using the same code
    or recording an employee on the same date. Rebuilding is idempotent: new
    databases already have the intended constraints and are left untouched.
    """
    needs_employees = ('code',) in _unique_indexes(conn, 'employees')
    needs_attendance = ('employee_id', 'attendance_date') in _unique_indexes(conn, 'attendance')
    if not needs_employees and not needs_attendance:
        return

    # These DDL operations must run with FK enforcement disabled because the
    # parent employees table is referenced by operational tables. The data is
    # copied with identical primary keys and valid relationships are restored
    # before enforcement is enabled again.
    conn.commit()
    conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
    try:
        if needs_employees:
            conn.exec_driver_sql("""
                CREATE TABLE employees_new (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    code VARCHAR(20) NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    job_title VARCHAR(100), department VARCHAR(100),
                    salary FLOAT, daily_rate FLOAT, phone VARCHAR(20),
                    national_id VARCHAR(20), area VARCHAR(100), hire_date DATE,
                    status VARCHAR(20), project_id INTEGER REFERENCES projects(id),
                    CONSTRAINT uq_employee_code_project UNIQUE (code, project_id)
                )
            """)
            conn.exec_driver_sql("""
                INSERT INTO employees_new
                    (id, code, name, job_title, department, salary, daily_rate,
                     phone, national_id, area, hire_date, status, project_id)
                SELECT id, code, name, job_title, department, salary, daily_rate,
                       phone, national_id, area, hire_date, status, project_id
                FROM employees
            """)
            conn.exec_driver_sql("DROP TABLE employees")
            conn.exec_driver_sql("ALTER TABLE employees_new RENAME TO employees")

        if needs_attendance:
            conn.exec_driver_sql("""
                CREATE TABLE attendance_new (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                    attendance_date DATE NOT NULL, status INTEGER,
                    workers_count FLOAT, project_id INTEGER REFERENCES projects(id),
                    CONSTRAINT uq_emp_date_project UNIQUE (employee_id, attendance_date, project_id)
                )
            """)
            conn.exec_driver_sql("""
                INSERT INTO attendance_new
                    (id, employee_id, attendance_date, status, workers_count, project_id)
                SELECT id, employee_id, attendance_date, status, workers_count, project_id
                FROM attendance
            """)
            conn.exec_driver_sql("DROP TABLE attendance")
            conn.exec_driver_sql("ALTER TABLE attendance_new RENAME TO attendance")
        conn.commit()
    finally:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")


def get_db() -> Session:
    """Return a fresh database session. Caller MUST call db.close() in a finally block."""
    return SessionLocal()
