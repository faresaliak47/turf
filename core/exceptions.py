"""
core/exceptions.py — Shared application exception types.

Services raise these instead of letting raw SQLAlchemy/db exceptions leak
into UI code, so both the Streamlit pages and the future PySide6 windows
can catch one small, well-known set of error types instead of each
re-implementing its own error handling around SQLAlchemy internals.

These are additive — existing services that already return
`(success: bool, message: str)` tuples (the established pattern in this
codebase; see services/auth.py, services/attendance_service.py) are left
exactly as they are. New service functions added in Phase 4A follow the
same tuple-return convention for consistency, and use these exception
types only for programming-error-style situations (e.g. calling code
passing an out-of-scope project_id) rather than for expected/user-facing
validation failures.
"""


class AppError(Exception):
    """Base class for all application-specific errors."""


class ProjectScopeError(AppError):
    """
    Raised when an operation is attempted against a record that does not
    belong to the given project_id.

    This is the "project isolation" guard rail: every CRUD service
    function that accepts a project_id must verify the target record's
    own project_id matches before mutating it, and raise this (or return
    a failure tuple, depending on the function's existing convention)
    instead of silently succeeding or silently doing nothing.
    """


class ValidationError(AppError):
    """Raised for invalid input caught at the service layer before any
    database write is attempted (e.g. non-positive amounts, missing
    required fields)."""


class NotFoundError(AppError):
    """Raised when a record looked up by primary key does not exist."""
