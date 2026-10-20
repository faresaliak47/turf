"""
tests/test_core.py — core.state / core.cache unit tests (Phase 4A Step
15). These need no database at all, but still import tests._bootstrap
first for consistency with every other test module (and because it's
harmless/cheap even here).
"""
import unittest
import time
from tests import _bootstrap  # noqa: F401

from core.state import get_state, state_get, state_set, state_pop, state_clear, reset_memory_state_for_tests
from core.cache import cached_data, cached_resource


class TestCoreState(unittest.TestCase):
    def setUp(self):
        reset_memory_state_for_tests()

    def test_set_and_get(self):
        state_set('foo', 'bar')
        self.assertEqual(state_get('foo'), 'bar')

    def test_get_missing_key_returns_default(self):
        self.assertIsNone(state_get('does_not_exist'))
        self.assertEqual(state_get('does_not_exist', 'fallback'), 'fallback')

    def test_pop_removes_key(self):
        state_set('temp', 123)
        popped = state_pop('temp')
        self.assertEqual(popped, 123)
        self.assertIsNone(state_get('temp'))

    def test_clear_specific_keys(self):
        state_set('a', 1)
        state_set('b', 2)
        state_clear(['a'])
        self.assertIsNone(state_get('a'))
        self.assertEqual(state_get('b'), 2)

    def test_clear_all(self):
        state_set('a', 1)
        state_set('b', 2)
        state_clear()
        self.assertIsNone(state_get('a'))
        self.assertIsNone(state_get('b'))

    def test_falls_back_to_memory_dict_outside_streamlit(self):
        """No live Streamlit script is running in the test process, so
        get_state() must return the in-memory fallback, not attempt to
        touch st.session_state (which would raise outside a real run)."""
        store = get_state()
        self.assertIsInstance(store, dict)


class TestCoreCache(unittest.TestCase):
    def test_cached_data_returns_same_value_for_same_args(self):
        calls = {'count': 0}

        @cached_data(ttl=None)
        def expensive(x):
            calls['count'] += 1
            return x * 2

        self.assertEqual(expensive(5), 10)
        self.assertEqual(expensive(5), 10)
        self.assertEqual(calls['count'], 1, "second call with same args should be served from cache")

    def test_cached_data_different_args_not_shared(self):
        @cached_data(ttl=None)
        def square(x):
            return x * x

        self.assertEqual(square(2), 4)
        self.assertEqual(square(3), 9)

    def test_cached_data_clear_invalidates(self):
        calls = {'count': 0}

        @cached_data(ttl=None)
        def fn():
            calls['count'] += 1
            return calls['count']

        first = fn()
        self.assertEqual(fn(), first)  # cached
        fn.clear()
        second = fn()
        self.assertNotEqual(first, second, "value should change after .clear()")

    def test_cached_data_respects_ttl(self):
        calls = {'count': 0}

        @cached_data(ttl=0.05)
        def fn():
            calls['count'] += 1
            return calls['count']

        fn()
        fn()
        self.assertEqual(calls['count'], 1)
        time.sleep(0.1)
        fn()
        self.assertEqual(calls['count'], 2, "value should be recomputed after TTL expires")

    def test_cached_resource_has_no_ttl(self):
        calls = {'count': 0}

        @cached_resource()
        def fn():
            calls['count'] += 1
            return "logo-bytes"

        fn()
        fn()
        self.assertEqual(calls['count'], 1)


if __name__ == "__main__":
    unittest.main()
