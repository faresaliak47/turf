"""
tests/_bootstrap.py — MUST be the first import in every test module.

WHY THIS EXISTS
────────────────
`database/db.py` resolves the SQLite file path and creates the
SQLAlchemy `engine`/`SessionLocal` at MODULE IMPORT TIME (not lazily),
using `database.paths.get_db_path()`. That means the database location
is fixed the very first time `database.db` is imported anywhere in the
process — importing it again later, or monkeypatching afterwards, does
not change which file it's already connected to.

To guarantee the test suite can NEVER write to the real, per-installation
database (Phase 4A Step 15: "Use temporary/test databases. Do not modify
production data during tests."), this module:

  1. Points `TURF_HR_PRO_DB_PATH` (see database/paths.py's get_db_path()
     — a small, additive, backward-compatible override added in Phase 4A
     specifically to make this possible) at a fresh temp file, BEFORE
     `database.db` is imported for the first time in this process.
  2. Calls `init_db()` once to create the schema in that temp file.

Every test module must do `from tests import _bootstrap` (or `import
tests._bootstrap`) as its very first import, before importing anything
from `database`, `services`, `desktop`, or `page_modules` — Python only
runs a module's top-level code on its FIRST import in the process, so as
long as this file is imported before `database.db` anywhere, the
redirection is guaranteed to win regardless of which test file pytest or
unittest happens to collect/import first.
"""
import os
import sys
import tempfile

if "TURF_HR_PRO_DB_PATH" not in os.environ:
    _tmp_dir = tempfile.mkdtemp(prefix="turf_hr_pro_tests_")
    os.environ["TURF_HR_PRO_DB_PATH"] = os.path.join(_tmp_dir, "test_hr.db")
    print(f"[tests/_bootstrap] Using isolated test database: {os.environ['TURF_HR_PRO_DB_PATH']}", file=sys.stderr)

from database.db import init_db  # noqa: E402  (must come after the env var is set)

init_db()
