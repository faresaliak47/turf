"""
core/state.py — UI-agnostic session/application state.

WHY THIS EXISTS
────────────────
Before Phase 4, `services/auth.py` and `services/projects.py` read and
wrote `st.session_state` directly. That works fine for the Streamlit app
(one script rerun = one "request", session_state persists across reruns
for one browser tab) but ties the *business logic* — who's logged in,
which project is selected — to a specific UI toolkit. A PySide6 desktop
window has no `st.session_state`, so those services could not have been
called from PySide6 without this abstraction.

WHAT IT PROVIDES
─────────────────
`get_state()` returns a mapping-like object (supports `[]`, `.get()`,
`.pop()`, `.clear()`, `in`) that is:
  - `st.session_state` itself, whenever this code is actually running
    inside a live Streamlit script (detected via Streamlit's own
    ScriptRunContext — not just "is streamlit installed"). This means
    the Streamlit app's behavior is byte-for-byte unchanged: every read
    and write still goes through the exact same st.session_state object
    Streamlit already manages per browser session.
  - a plain process-wide dict everywhere else — a normal Python script,
    the test suite, or the PySide6 desktop app. A desktop app is
    single-user/single-session by nature, so a process-wide dict has
    exactly the right semantics (one desktop window = one "session").

Services should use the small wrapper functions below (`state_get`,
`state_set`, `state_pop`, `state_clear`) rather than calling
`get_state()` directly in most cases — they read a little closer to the
`st.session_state.get(...)` calls they replace.
"""
from __future__ import annotations
from typing import Any, Iterable


def _streamlit_session_available() -> bool:
    """
    True only when Streamlit is installed AND a script is actually
    running right now (there is an active ScriptRunContext). Importing
    streamlit successfully is NOT enough — reading/writing
    st.session_state outside of a live script run raises, so every
    caller in this module must check this before touching it.
    """
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx() is not None
    except Exception:
        return False


# Process-wide fallback store, used whenever a live Streamlit session is
# not available (desktop app, tests, plain scripts, or Streamlit not
# installed at all). A plain dict already implements every operation this
# module needs (`[]`, `.get`, `.pop`, `.clear`, `in`), so no wrapper class
# is needed.
_memory_state: dict[str, Any] = {}


def get_state():
    """Return the active state store — st.session_state under a live
    Streamlit run, or the shared in-memory dict otherwise."""
    if _streamlit_session_available():
        import streamlit as st
        return st.session_state
    return _memory_state


def state_get(key: str, default: Any = None) -> Any:
    return get_state().get(key, default)


def state_set(key: str, value: Any) -> None:
    get_state()[key] = value


def state_pop(key: str, default: Any = None) -> Any:
    return get_state().pop(key, default)


def state_contains(key: str) -> bool:
    return key in get_state()


def state_clear(keys: Iterable[str] | None = None) -> None:
    """Clear specific keys, or the whole state store if `keys` is None."""
    if keys is None:
        get_state().clear()
        return
    for k in keys:
        state_pop(k, None)


def reset_memory_state_for_tests() -> None:
    """Test-only helper: wipes the process-wide fallback store between
    test cases so one test's desktop-mode session state can't leak into
    the next. No-op effect on the real st.session_state path (each
    Streamlit session already has its own isolated session_state)."""
    _memory_state.clear()
