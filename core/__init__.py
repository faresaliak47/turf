"""
core/ — Reusable application infrastructure, shared by both the existing
Streamlit UI and the new PySide6 desktop UI.

Nothing in this package imports Streamlit or PySide6 directly (aside from
optional, try/except-guarded imports inside core.state / core.cache used
purely to detect which UI environment is currently running). Business
logic in services/ should depend on `core`, never on a specific UI
toolkit.
"""
from core import state, cache, config, exceptions, logging_config  # noqa: F401
