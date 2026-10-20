"""
Project (multi-project) support service.

Centralizes everything related to which "project" is currently selected:
listing/creating projects, and reading/writing the current selection to
the UI-agnostic session state (core.state — backed by st.session_state
under Streamlit, or a plain in-memory store under the PySide6 desktop
app / tests), and persisting it per-user so it's remembered across
logins.
"""
from database.db import get_db, DEFAULT_PROJECT_NAME
from database.models import Project, User, Employee, Expense, ReceivedFund
from core.state import state_get, state_set
from core.cache import cached_data
from core.config import PROJECT_LIST_CACHE_TTL


@cached_data(ttl=PROJECT_LIST_CACHE_TTL, show_spinner=False)
def _list_projects_cached():
    """Cached read of every project row, as plain (id, name) tuples so the
    cache doesn't hold onto detached ORM objects across reruns. This list
    rarely changes but was being re-queried on every single rerun (the
    sidebar reads it on every page load), which was pure overhead.
    Invalidated explicitly by create_project() whenever a project is added.
    """
    db = get_db()
    try:
        return [(p.id, p.name) for p in db.query(Project).order_by(Project.name).all()]
    finally:
        db.close()


def list_projects(db=None):
    """Return all projects ordered by name.

    When called without an explicit session (the common case: sidebar,
    dropdowns, etc.) this is served from a short-lived cache instead of
    hitting the database on every rerun. When a caller supplies its own
    `db` session (e.g. inside a larger transaction), the cache is bypassed
    and the database is queried directly, to guarantee read-your-writes
    consistency there.
    """
    if db is not None:
        return db.query(Project).order_by(Project.name).all()

    rows = _list_projects_cached()
    return [Project(id=pid, name=name) for pid, name in rows]


def get_default_project_id(db=None) -> int | None:
    """Return the id of the auto-created default project, if it still
    exists (it always does after database.db.init_db() has run once)."""
    owns_session = db is None
    db = db or get_db()
    try:
        p = db.query(Project).filter(Project.name == DEFAULT_PROJECT_NAME).first()
        return p.id if p else None
    finally:
        if owns_session:
            db.close()


def create_project(name: str, code: str = None) -> Project:
    """Create a new project (or return the existing one if the name is
    already taken, so a double-submit doesn't raise an IntegrityError)."""
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم المشروع مطلوب")
    db = get_db()
    try:
        existing = db.query(Project).filter(Project.name == name).first()
        if existing:
            return existing
        project = Project(name=name, code=(code or "").strip() or None)
        db.add(project)
        db.commit()
        db.refresh(project)
        return project
    finally:
        db.close()
        _list_projects_cached.clear()


def get_current_project_id() -> int | None:
    """
    The single source of truth for "which project is selected right now".
    Falls back to the user's remembered last project, then the default
    project, the first time it's read in a session (components/layout.py's
    render_project_selector() calls this to initialize the sidebar).
    """
    pid = state_get('current_project_id')
    if pid:
        return pid

    # Not set yet this session — try the logged-in user's remembered choice.
    user_id = state_get('user_id')
    if user_id:
        db = get_db()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user and user.last_project_id:
                projects_ids = {p.id for p in db.query(Project).all()}
                if user.last_project_id in projects_ids:
                    state_set('current_project_id', user.last_project_id)
                    return user.last_project_id
        finally:
            db.close()

    # Fall back to the default project, or simply the first project that
    # exists (covers the rare case the default project was renamed/deleted).
    default_id = get_default_project_id()
    if default_id:
        state_set('current_project_id', default_id)
        return default_id

    projects = list_projects()
    if projects:
        state_set('current_project_id', projects[0].id)
        return projects[0].id

    return None


def set_current_project(project_id: int, remember: bool = True):
    """Switch the active project for the rest of this session, and — for a
    logged-in user — persist the choice so it's restored on next login."""
    state_set('current_project_id', project_id)
    if remember:
        user_id = state_get('user_id')
        if user_id:
            db = get_db()
            try:
                user = db.query(User).filter(User.id == user_id).first()
                if user:
                    user.last_project_id = project_id
                    db.commit()
            finally:
                db.close()


def delete_project(project_id: int) -> tuple[bool, str]:
    """
    Delete a project, identified by its primary key, along with ALL data
    scoped to it — Employees and everything that cascades from them
    (Attendance/Overtime/Advances/PayrollCache), plus Expenses and
    ReceivedFunds — inside a single transaction, so a failure partway
    through leaves nothing deleted (see the rollback below).

    Employees are removed through the ORM (`db.delete(emp)`) rather than
    a bulk `.delete()` query, so SQLAlchemy walks Employee's
    cascade='all, delete-orphan' relationships (see database/models.py)
    and deletes their Attendance/Overtime/Advance/PayrollCache rows
    first — this is what keeps the deletion FK-safe and orphan-free
    without this function needing to touch those four tables directly.
    Expense/ReceivedFund have no such ORM relationship to Employee (they
    only carry their own `project_id`), so they're removed directly.

    Any user whose remembered "last project" (users.last_project_id) was
    this one is repointed at NULL first, so that FK can't block the
    project delete either — they simply fall back to the default
    project on next login (see get_current_project_id()).

    Never touches any other project's data, and refuses to remove the
    last remaining project (the whole app assumes at least one project
    always exists — see get_current_project_id()'s fallback chain).

    Returns (success, message).
    """
    db = get_db()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return False, "المشروع غير موجود."

        if db.query(Project).count() <= 1:
            return False, "لا يمكن حذف المشروع الوحيد المتبقي في النظام."

        project_name = project.name

        emp_count  = db.query(Employee).filter(Employee.project_id == project_id).count()
        exp_count  = db.query(Expense).filter(Expense.project_id == project_id).count()
        fund_count = db.query(ReceivedFund).filter(ReceivedFund.project_id == project_id).count()

        # Unlink any user's "remembered project" pointer first, so the
        # FK on users.last_project_id can't block the project delete.
        db.query(User).filter(User.last_project_id == project_id).update(
            {User.last_project_id: None}, synchronize_session=False
        )

        # Delete every Employee through the ORM so cascade='all,
        # delete-orphan' removes their Attendance/Overtime/Advance/
        # PayrollCache rows too — no orphan records, no broken FKs.
        employees = db.query(Employee).filter(Employee.project_id == project_id).all()
        for emp in employees:
            db.delete(emp)

        # Expense / ReceivedFund carry project_id directly (no Employee
        # relationship to cascade through), so remove them explicitly.
        db.query(Expense).filter(Expense.project_id == project_id).delete(synchronize_session=False)
        db.query(ReceivedFund).filter(ReceivedFund.project_id == project_id).delete(synchronize_session=False)

        # Flush everything above BEFORE deleting the Project row itself.
        # Attendance/Overtime/Advance/PayrollCache/Employee/Expense/
        # ReceivedFund each carry their own `project_id` FK straight to
        # `projects` (in addition to Attendance/Overtime/Advance/
        # PayrollCache's `employee_id` FK to Employee) — but there's no
        # SQLAlchemy `relationship()` wired between Project and any of
        # them, so the unit-of-work has no way to know it must order
        # their deletes before the Project delete. Without this explicit
        # flush, SQLAlchemy is free to emit "DELETE FROM projects" before
        # those rows are actually gone, which trips SQLite's FK check.
        db.flush()

        db.delete(project)
        db.commit()

        if emp_count or exp_count or fund_count:
            parts = []
            if emp_count:
                parts.append(f"{emp_count} موظف (وما يرتبط بهم من حضور/أوفر تايم/سلف/رواتب)")
            if exp_count:
                parts.append(f"{exp_count} مصروف")
            if fund_count:
                parts.append(f"{fund_count} سجل من الأموال الواردة")
            return True, (
                f"تم حذف المشروع «{project_name}» بنجاح، مع حذف كل البيانات المرتبطة به: "
                + "، ".join(parts) + "."
            )

        return True, f"تم حذف المشروع «{project_name}» بنجاح."
    except Exception as e:
        db.rollback()
        return False, f"خطأ أثناء حذف المشروع: {e}"
    finally:
        db.close()
        _list_projects_cached.clear()


def get_current_project_name() -> str:
    pid = get_current_project_id()
    if not pid:
        return ""
    return get_project_name(pid)


def get_project_name(project_id: int) -> str:
    """Return the name of a specific project by id (unlike
    get_current_project_name(), not tied to the current session's
    selection) — e.g. used by services/excel_export.py to build a
    report filename for whichever project was actually exported."""
    if not project_id:
        return ""
    db = get_db()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        return p.name if p else ""
    finally:
        db.close()
