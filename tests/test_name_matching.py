"""
tests/test_name_matching.py — Smart Employee Name Matching.

Covers services/name_matching.py directly, plus its wiring into
services/attendance_service.py's smart-paste attendance (the concrete
place this was requested for).
"""
import unittest
from tests import _bootstrap  # noqa: F401 — must be first
from tests.helpers import make_project, make_employee, reset_session_state, unique

from services.name_matching import (
    normalize_arabic_name, build_employee_name_index, match_employee_by_name,
)
from services import attendance_service


class TestNormalizeArabicName(unittest.TestCase):
    def test_alef_variants_unify(self):
        self.assertEqual(normalize_arabic_name("أحمد"), normalize_arabic_name("احمد"))
        self.assertEqual(normalize_arabic_name("إحمد"), normalize_arabic_name("احمد"))
        self.assertEqual(normalize_arabic_name("آحمد"), normalize_arabic_name("احمد"))

    def test_abu_variants_unify(self):
        # "أبو" -> alef normalization alone turns it into "ابو"
        self.assertEqual(
            normalize_arabic_name("شريف أبو العزم"),
            normalize_arabic_name("شريف ابو العزم"),
        )

    def test_tashkeel_removed(self):
        self.assertEqual(
            normalize_arabic_name("شَرِيف أبو العزم"),
            normalize_arabic_name("شريف ابو العزم"),
        )

    def test_extra_and_surrounding_whitespace_collapsed(self):
        self.assertEqual(
            normalize_arabic_name("  شريف   أبو   العزم  "),
            normalize_arabic_name("شريف ابو العزم"),
        )

    def test_full_example_from_spec(self):
        """The exact example from the task: 'شَرِيف أبو العزم' must match
        'شريف ابو العزم' after normalization."""
        db_name    = "شريف ابو العزم"
        typed_name = "شَرِيف أبو العزم"
        self.assertEqual(normalize_arabic_name(db_name), normalize_arabic_name(typed_name))

    def test_empty_and_none_safe(self):
        self.assertEqual(normalize_arabic_name(""), "")
        self.assertEqual(normalize_arabic_name(None), "")


class TestMatchEmployeeByName(unittest.TestCase):
    def setUp(self):
        reset_session_state()
        self.project = make_project()
        self.emp = make_employee(self.project.id, code=unique("NM"), name="شريف ابو العزم")

    def test_matches_with_diacritics_and_alef_variant_and_spacing(self):
        employees = [self.emp]
        emp, status = match_employee_by_name("  شَرِيف   أبو العزم  ", employees=employees)
        self.assertEqual(status, "matched")
        self.assertIsNotNone(emp)
        self.assertEqual(emp.id, self.emp.id)
        # Original DB name must remain untouched.
        self.assertEqual(emp.name, "شريف ابو العزم")

    def test_no_match_returns_unmatched(self):
        employees = [self.emp]
        emp, status = match_employee_by_name("موظف غير موجود اطلاقا", employees=employees)
        self.assertIsNone(emp)
        self.assertEqual(status, "unmatched")

    def test_ambiguous_match_is_never_guessed(self):
        """Two employees whose names normalize identically must never be
        auto-resolved — the caller gets 'ambiguous', not a random pick."""
        emp2 = make_employee(self.project.id, code=unique("NM"), name="شريف ابو العزم")
        employees = [self.emp, emp2]
        index = build_employee_name_index(employees)
        emp, status = match_employee_by_name("شريف ابو العزم", name_index=index)
        self.assertIsNone(emp)
        self.assertEqual(status, "ambiguous")

    def test_ambiguous_substring_match_is_never_guessed(self):
        """Two distinct employees that could both plausibly match a
        partial name must not be auto-resolved either."""
        emp2 = make_employee(self.project.id, code=unique("NM"), name="شريف كمال")
        employees = [self.emp, emp2]
        index = build_employee_name_index(employees)
        emp, status = match_employee_by_name("شريف", name_index=index)
        self.assertIsNone(emp)
        self.assertEqual(status, "ambiguous")


class TestSmartAttendanceUsesNameMatching(unittest.TestCase):
    """End-to-end: process_smart_attendance() must resolve a diacritic /
    alef-variant / extra-spaced name to the correct employee id, and
    must never silently invent a match for an ambiguous name."""

    def setUp(self):
        reset_session_state()
        self.project = make_project()
        from core.state import state_set
        state_set('current_project_id', self.project.id)
        self.emp = make_employee(
            self.project.id, code=unique("NM"), name="شريف ابو العزم", status="Active",
        )

    def test_smart_attendance_matches_variant_spelling(self):
        text = "01/06/2026\nشَرِيف أبو العزم"
        result = attendance_service.process_smart_attendance(text)
        self.assertTrue(result["success"])
        self.assertEqual(result["saved"], 1)
        self.assertEqual(len(result["unmatched"]), 0)
        self.assertEqual(result["matched"][0]["name"], "شريف ابو العزم")


if __name__ == "__main__":
    unittest.main()
