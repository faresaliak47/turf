"""
tests/helpers.py — Shared test utilities.

Import `tests._bootstrap` FIRST in every test module that imports this
file (see tests/_bootstrap.py's docstring for why).
"""
from tests import _bootstrap  # noqa: F401  (ensures DB isolation before anything else below)

import uuid
from datetime import date

from database.db import get_db
from database.models import Project, Employee, User
from core.state import reset_memory_state_for_tests, state_set
from services.auth import make_password_hash


def unique(prefix: str) -> str:
    """A short-unique string for names/codes that must not collide
    between test runs against the same temp database (tests reuse the
    one temp DB created by _bootstrap for the whole process)."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def reset_session_state():
    """Clear the in-memory (desktop/test-mode) session state between
    tests, so one test's logged-in user / selected project can't leak
    into the next. No-op on the real Streamlit session_state path."""
    reset_memory_state_for_tests()


def make_project(name: str = None) -> Project:
    db = get_db()
    try:
        p = Project(name=name or unique("Project"), is_active=True)
        db.add(p)
        db.commit()
        db.refresh(p)
        return p
    finally:
        db.close()


def make_employee(project_id: int, code: str = None, name: str = None,
                   daily_rate: float = 100.0, salary: float = 3000.0,
                   status: str = "Active") -> Employee:
    db = get_db()
    try:
        e = Employee(
            code=code or unique("E"), name=name or unique("Employee"),
            daily_rate=daily_rate, salary=salary, status=status,
            project_id=project_id,
        )
        db.add(e)
        db.commit()
        db.refresh(e)
        return e
    finally:
        db.close()


def make_user(username: str = None, password: str = "Passw0rd!", role: str = "admin") -> User:
    db = get_db()
    try:
        u = User(
            username=username or unique("user"),
            password_hash=make_password_hash(password),
            full_name="Test User",
            role=role,
            is_active=True,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u
    finally:
        db.close()


def login_as(user: User):
    """Simulate a logged-in session without going through the actual
    password check — used when a test only needs 'someone is logged in
    as this role', not to re-test the login flow itself (that's
    test_auth.py's job)."""
    state_set('logged_in', True)
    state_set('user_id', user.id)
    state_set('username', user.username)
    state_set('full_name', user.full_name)
    state_set('user_role', user.role)


def today() -> date:
    return date.today()
