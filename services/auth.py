"""Authentication service for HR Pro."""
import hashlib
import secrets
from database.db import get_db
from database.models import User
from core.state import state_get, state_set, state_clear
from core.logging_config import get_logger

_log = get_logger(__name__)


# ── Password hashing (sha256 + salt) ──────────────────────────────────────────
def _hash_password(password: str, salt: str = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return hashed, salt


def _verify_password(password: str, stored_hash: str) -> bool:
    """stored_hash format: salt$hash"""
    try:
        salt, hashed = stored_hash.split('$', 1)
        computed, _ = _hash_password(password, salt)
        return computed == hashed
    except Exception as e:
        print(f"[auth] Password verification error: {e}")
        return False


def make_password_hash(password: str) -> str:
    hashed, salt = _hash_password(password)
    return f"{salt}${hashed}"


# ── Role permissions ───────────────────────────────────────────────────────────
ROLE_PERMISSIONS = {
    'admin':      ['dashboard', 'employees', 'attendance', 'overtime', 'advances', 'discounts', 'payroll', 'reports', 'user_management', 'plant_deliveries', 'accountant_handover'],
    # 'discounts' is deliberately HR-only (not accountant) — deciding who
    # gets deducted and why (lateness, unexcused absence...) is an HR call.
    # The accountant role still sees the resulting totals reflected in
    # 'payroll' (net salary already accounts for discounts), just can't
    # create/edit them directly.
    'hr':         ['dashboard', 'employees', 'attendance', 'discounts', 'reports'],
    'accountant': ['dashboard', 'payroll', 'advances', 'reports', 'plant_deliveries', 'accountant_handover'],
    'viewer':     ['dashboard'],
}

ROLE_LABELS = {
    'admin':      '🔑 مدير النظام',
    'hr':         '👥 مسؤول الموارد البشرية',
    'accountant': '📊 محاسب',
    'viewer':     '👁️ مشاهد',
}


def can_access(page_key: str) -> bool:
    role = state_get('user_role', 'viewer')
    return page_key in ROLE_PERMISSIONS.get(role, [])


def is_logged_in() -> bool:
    return state_get('logged_in', False)


def needs_setup() -> bool:
    """Return True if no users exist yet (first-run)."""
    db = get_db()
    try:
        return db.query(User).count() == 0
    finally:
        db.close()


def login(username: str, password: str) -> bool:
    db = get_db()
    try:
        user = db.query(User).filter(
            User.username == username,
            User.is_active == True
        ).first()
        if user and _verify_password(password, user.password_hash):
            state_set('logged_in', True)
            state_set('user_id',   user.id)
            state_set('username',  user.username)
            state_set('full_name', user.full_name)
            state_set('user_role', user.role)
            _log.info("Login succeeded for user_id=%s username=%s", user.id, user.username)
            return True
        _log.info("Login failed for username=%s", username)
        return False
    finally:
        db.close()


def logout():
    keys = [
        'logged_in', 'user_id', 'username', 'full_name', 'user_role',
        'payroll_df', 'payroll_month', 'payroll_year',
    ]
    state_clear(keys)
    # Explicitly mark as logged out so the login page renders
    state_set('logged_in', False)


# ── User management ────────────────────────────────────────────────────────────
def create_user(username: str, password: str, full_name: str, role: str = 'viewer') -> tuple[bool, str]:
    db = get_db()
    try:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            return False, "اسم المستخدم مستخدم بالفعل."
        user = User(
            username=username,
            password_hash=make_password_hash(password),
            full_name=full_name,
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        return True, "تم إنشاء المستخدم بنجاح."
    except Exception as e:
        db.rollback()
        return False, f"خطأ: {e}"
    finally:
        db.close()


def update_user(user_id: int, full_name: str, role: str) -> tuple[bool, str]:
    db = get_db()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False, "المستخدم غير موجود."
        user.full_name = full_name
        user.role = role
        db.commit()
        return True, "تم تحديث بيانات المستخدم."
    except Exception as e:
        db.rollback()
        return False, f"خطأ: {e}"
    finally:
        db.close()


def reset_password(user_id: int, new_password: str) -> tuple[bool, str]:
    db = get_db()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False, "المستخدم غير موجود."
        user.password_hash = make_password_hash(new_password)
        db.commit()
        return True, "تم تغيير كلمة المرور بنجاح."
    except Exception as e:
        db.rollback()
        return False, f"خطأ: {e}"
    finally:
        db.close()


def set_user_active(user_id: int, is_active: bool) -> tuple[bool, str]:
    db = get_db()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False, "المستخدم غير موجود."
        user.is_active = is_active
        db.commit()
        status = "تم تفعيل" if is_active else "تم تعطيل"
        return True, f"{status} المستخدم بنجاح."
    except Exception as e:
        db.rollback()
        return False, f"خطأ: {e}"
    finally:
        db.close()


def delete_user(user_id: int, current_user_id: int) -> tuple[bool, str]:
    """Permanently delete a user account, regardless of role.

    The only restriction is self-deletion — mirrors the existing
    is_self guard used for the disable/enable toggle in
    user_management.py, so a user can never lock themselves out.
    """
    if user_id == current_user_id:
        return False, "لا يمكنك حذف حسابك الخاص."
    db = get_db()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False, "المستخدم غير موجود."
        db.delete(user)
        db.commit()
        return True, f"تم حذف المستخدم «{user.full_name}» نهائياً."
    except Exception as e:
        db.rollback()
        return False, f"خطأ: {e}"
    finally:
        db.close()


def get_all_users():
    db = get_db()
    try:
        return db.query(User).order_by(User.id).all()
    finally:
        db.close()
