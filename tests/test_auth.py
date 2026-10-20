"""
tests/test_auth.py — Authentication (Phase 4A Step 15).

Runs entirely outside Streamlit (services.auth is now backed by
core.state — see Phase 4A's backend decoupling), which itself proves
Step 17 for this specific module: no live Streamlit session exists in
the test process, so core.state.get_state() falls back to the in-memory
store automatically, and login/logout/can_access all work identically.
"""
import unittest
from tests import _bootstrap  # noqa: F401 — must be first
from tests.helpers import make_user, reset_session_state

from services import auth


class TestAuth(unittest.TestCase):
    def setUp(self):
        reset_session_state()

    def test_valid_login_succeeds(self):
        make_user(username="gooduser", password="CorrectHorse123", role="admin")
        ok = auth.login("gooduser", "CorrectHorse123")
        self.assertTrue(ok)
        self.assertTrue(auth.is_logged_in())

    def test_invalid_password_rejected(self):
        make_user(username="gooduser2", password="CorrectHorse123", role="admin")
        ok = auth.login("gooduser2", "WrongPassword")
        self.assertFalse(ok)
        self.assertFalse(auth.is_logged_in())

    def test_unknown_username_rejected(self):
        ok = auth.login("does_not_exist_at_all", "whatever")
        self.assertFalse(ok)

    def test_inactive_user_cannot_login(self):
        from database.db import get_db
        user = make_user(username="inactiveuser", password="pw123456", role="viewer")
        db = get_db()
        try:
            u = db.query(type(user)).filter_by(id=user.id).first()
            u.is_active = False
            db.commit()
        finally:
            db.close()
        ok = auth.login("inactiveuser", "pw123456")
        self.assertFalse(ok)

    def test_logout_clears_session(self):
        make_user(username="logoutuser", password="pw123456", role="admin")
        auth.login("logoutuser", "pw123456")
        self.assertTrue(auth.is_logged_in())
        auth.logout()
        self.assertFalse(auth.is_logged_in())

    def test_role_permissions_admin_has_full_access(self):
        make_user(username="adminuser", password="pw123456", role="admin")
        auth.login("adminuser", "pw123456")
        for page in ['dashboard', 'employees', 'attendance', 'overtime', 'advances', 'payroll', 'reports']:
            self.assertTrue(auth.can_access(page), f"admin should access {page}")

    def test_role_permissions_viewer_is_restricted(self):
        make_user(username="vieweruser", password="pw123456", role="viewer")
        auth.login("vieweruser", "pw123456")
        self.assertTrue(auth.can_access('dashboard'))
        self.assertFalse(auth.can_access('user_management'))
        self.assertFalse(auth.can_access('payroll'))

    def test_password_never_returned_in_plaintext(self):
        """Sanity check on the hashing helper itself — make_password_hash
        must never return the plaintext password."""
        hashed = auth.make_password_hash("SuperSecret123")
        self.assertNotIn("SuperSecret123", hashed)
        self.assertIn("$", hashed)  # salt$hash format


if __name__ == "__main__":
    unittest.main()
