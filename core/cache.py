"""
core/cache.py — UI-agnostic function-result caching.

WHY THIS EXISTS
────────────────
Before Phase 4, `services/payroll_service.py` and `services/projects.py`
decorated functions directly with `@st.cache_data(...)` / a Streamlit
cache. That ties the payroll/project-list caching strategy to Streamlit
being installed and running, which breaks the PySide6 desktop app and
prevents the service layer from being imported without Streamlit
(Phase 4A Step 17 requirement).

WHAT IT PROVIDES
─────────────────
`cached_data(ttl=..., show_spinner=...)` is a decorator with the same
call/`.clear()` contract every caller in this codebase already relies on
(see services/payroll_service.py's `clear_payroll_cache()` calling
`_calculate_payroll_cached.clear()`, and services/projects.py's
`create_project()` calling `_list_projects_cached.clear()`):

  - Under a live Streamlit script run, this delegates straight to
    `st.cache_data(ttl=..., show_spinner=...)` — identical behavior to
    before this refactor, same cache keying (by call arguments), same
    invalidation (`.clear()`).
  - Everywhere else (desktop app, tests, plain scripts, or Streamlit not
    installed), it falls back to a small in-memory TTL cache with the
    same call/`.clear()` surface, so callers don't need an `if running
    under streamlit` branch of their own.

`cached_resource(...)` is the equivalent of `st.cache_resource` (no TTL —
cached for the life of the process), used the same way.
"""
from __future__ import annotations
import time
import functools
from typing import Callable, Optional

from core.state import _streamlit_session_available


class _SimpleTTLCache:
    """
    Minimal process-wide TTL cache used as the non-Streamlit fallback.
    Keyed on the wrapped function's call arguments (mirrors
    st.cache_data's own keying-by-arguments behavior). Not thread-safe
    beyond what the GIL already gives plain dict operations — acceptable
    for a single-user desktop app and for tests.
    """

    def __init__(self, func: Callable, ttl: Optional[float]):
        self._func = func
        self._ttl = ttl
        self._store: dict[tuple, tuple[float, object]] = {}
        functools.update_wrapper(self, func)

    @staticmethod
    def _key(args, kwargs):
        return (args, tuple(sorted(kwargs.items())))

    def __call__(self, *args, **kwargs):
        key = self._key(args, kwargs)
        now = time.monotonic()
        cached = self._store.get(key)
        if cached is not None:
            ts, value = cached
            if self._ttl is None or (now - ts) < self._ttl:
                return value
        value = self._func(*args, **kwargs)
        self._store[key] = (now, value)
        return value

    def clear(self):
        """Invalidate every cached entry for this function — matches
        st.cache_data's `.clear()` contract used throughout the codebase
        (clear_payroll_cache(), create_project(), etc.)."""
        self._store.clear()


def cached_data(ttl: Optional[float] = None, show_spinner: bool = False):
    """
    Decorator: cache a function's return value by its call arguments.

    Uses st.cache_data when a Streamlit script is actually running
    (identical behavior to the pre-Phase-4 code); otherwise falls back to
    an in-memory TTL cache with the same `.clear()` contract. Safe to
    import and apply even when Streamlit is not installed at all.
    """
    def decorator(func: Callable):
        if _streamlit_session_available():
            import streamlit as st
            return st.cache_data(ttl=ttl, show_spinner=show_spinner)(func)
        return _SimpleTTLCache(func, ttl)
    return decorator


def cached_resource(show_spinner: bool = False):
    """Same idea as cached_data, for values that should live for the
    whole process (e.g. a logo file's bytes) — no TTL, still supports
    `.clear()`."""
    def decorator(func: Callable):
        if _streamlit_session_available():
            import streamlit as st
            return st.cache_resource(show_spinner=show_spinner)(func)
        return _SimpleTTLCache(func, ttl=None)
    return decorator
