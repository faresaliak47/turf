import sys
import os
import logging
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
from datetime import date, timedelta
import hashlib

_startup_log = logging.getLogger("turf_hr.startup")

# ── Page config ─────────────────────────────────────────────
st.set_page_config(
    page_title='TURF Landscape Co. — HR Pro',
    page_icon='🌳',
    layout='wide',
    initial_sidebar_state='expanded'
)

try:
    # Keep all DB/auth imports in this guarded startup block as those modules
    # construct the SQLite engine during import. A failure must be logged with
    # its traceback instead of leaving Cloud with only a failed health check.
    from database.db import init_db, get_db
    from database.models import Employee, Attendance, Overtime, Advance, User
    from services.audit_service import audit_actor
    from services.auth import is_logged_in, logout, needs_setup, can_access, ROLE_LABELS
    from components.theme import inject_global_css

    inject_global_css()
    init_db()
except Exception:
    _startup_log.exception("TURF HR Pro failed during startup")
    st.error(
        "تعذر بدء التطبيق أثناء تهيئة قاعدة البيانات أو مكونات التشغيل. "
        "افتح Manage app ثم Logs لعرض سبب الخطأ الكامل."
    )
    st.stop()

# Daily attendance reminder scheduler (isolated module; idempotent per process).
try:
    from services.notification_service import start_scheduler
    start_scheduler()
except Exception as _e:
    print(f"[notifications] scheduler not started: {_e}")

# ─────────────────────────────────────────────
# SESSION HELPERS
# ─────────────────────────────────────────────
_APP_SECRET = os.environ.get("HRPRO_SESSION_SECRET", "hrpro-session-v1")


def _make_token(user_id: int, secret: str) -> str:
    return hashlib.sha256(f"{user_id}:{secret}".encode()).hexdigest()[:24]


def _restore_session_if_needed():
    if st.session_state.get('logged_in'):
        return
    params = st.query_params
    token  = params.get("_sid", "")
    uid    = params.get("_uid", "")
    if not token or not uid:
        return
    try:
        user_id = int(uid)
    except ValueError:
        return
    if token != _make_token(user_id, _APP_SECRET):
        st.query_params.clear()
        return
    db = get_db()
    try:
        user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
        if user:
            st.session_state.update({
                "logged_in": True,
                "user_id":   user.id,
                "username":  user.username,
                "full_name": user.full_name,
                "user_role": user.role
            })
    finally:
        db.close()


def _write_session_token():
    user_id = st.session_state.get('user_id')
    if not user_id:
        return
    token = _make_token(user_id, _APP_SECRET)
    st.query_params["_sid"] = token
    st.query_params["_uid"] = str(user_id)


def _clear_session_token():
    st.query_params.clear()


def _write_page_param(page_key: str):
    """Persist the currently open page in the URL so that a websocket
    reconnect (e.g. caused by split-screen / the tab losing focus) restores
    the same page instead of resetting back to the main menu."""
    if page_key:
        st.query_params["_page"] = page_key


_restore_session_if_needed()

# ── Setup wizard ─────────────────────────────
if needs_setup():
    from page_modules.setup_wizard import show_setup_wizard
    show_setup_wizard()
    st.stop()

# ── Auth ─────────────────────────────────────
if not is_logged_in():
    from page_modules.login import show_login
    show_login()
    st.stop()

_write_session_token()

# ── Sidebar + Routing ────────────────────────
from components.layout import (
    render_sidebar, render_project_selector, NAV_LABELS, NAV_ITEMS,
    apply_sidebar_collapse_css, render_sidebar_reopen_button, render_sidebar_brand,
)
from components.theme import COLORS

apply_sidebar_collapse_css()
render_sidebar_reopen_button()

# Keep the company identity first, then show the active project selector.
render_sidebar_brand()

# Project selector renders first so the rest of the sidebar (and every page
# rendered below it this run) sees the right st.session_state['current_project_id'].
render_project_selector()

extra = ([
    ("👤", "إدارة المستخدمين", "user_management"),
    ("🧾", "سجل التغييرات", "audit_log"),
] if can_access("user_management") else [])
selected = render_sidebar(extra_items=extra)

# ─────────────────────────────────────────────
# ROUTING
# ─────────────────────────────────────────────
# Routes by page KEY, not by list position — safe against NAV_ITEMS being
# reordered/extended (e.g. adding "discounts" in the middle of the list).
PAGE_KEYS = [item[2] for item in NAV_ITEMS]

_all_nav_items = NAV_ITEMS + extra
_all_nav_labels = [label for icon, label, _ in _all_nav_items]
_selected_key = ""
if selected in _all_nav_labels:
    _selected_key = _all_nav_items[_all_nav_labels.index(selected)][2]
elif selected in NAV_LABELS:
    _selected_key = NAV_ITEMS[NAV_LABELS.index(selected)][2]

# Pages opened from the top bar (user settings / notification settings) are not
# in the sidebar. They are routed through _page_override, which is dropped as
# soon as the user picks a different sidebar item.
if st.session_state.get("_last_nav_label") != selected:
    st.session_state.pop("_page_override", None)
st.session_state["_last_nav_label"] = selected
_override = st.session_state.get("_page_override")
if _override in ("user_settings", "notification_settings"):
    _selected_key = _override
_write_page_param(_selected_key)


def page_allowed(key: str) -> bool:
    return can_access(key)


_PAGE_MODULES = {
    'dashboard':       ('page_modules.dashboard',       True),
    'employees':       ('page_modules.employees',       False),
    'attendance':      ('page_modules.attendance',       False),
    'overtime':        ('page_modules.overtime',         False),
    'bulk_overtime':   ('page_modules.bulk_overtime',    False),
    'advances':        ('page_modules.advances',         False),
    'discounts':       ('page_modules.discounts',        False),
    'payroll':         ('page_modules.payroll',          False),
    'expenses':        ('page_modules.expenses',         True),
    'plant_deliveries': ('page_modules.plant_deliveries', False),
    'accountant_handover': ('page_modules.accountant_handover', False),
    'reports':         ('page_modules.reports',          False),
    'user_management': ('page_modules.user_management',  False),
    'audit_log':       ('page_modules.audit_log',        False),
    'user_settings':          ('page_modules.user_settings',         True),   # any logged-in user
    'notification_settings':  ('page_modules.notification_settings', True),   # permission checked inside the page
}
# `permission_key`: 'bulk_overtime' reuses the 'overtime' permission (same
# as the original code), everything else uses its own page key.
_PERMISSION_KEY_OVERRIDES = {'bulk_overtime': 'overtime', 'audit_log': 'user_management'}

import importlib

module_path, always_allowed = _PAGE_MODULES.get(_selected_key, (None, False))
if module_path:
    permission_key = _PERMISSION_KEY_OVERRIDES.get(_selected_key, _selected_key)
    if always_allowed or page_allowed(permission_key):
        mod = importlib.import_module(module_path)
        with audit_actor(st.session_state.get('user_id'), st.session_state.get('username')):
            mod.show()
    else:
        st.warning("ليس لديك صلاحية الوصول لهذا القسم.")
