"""
Application path resolution — Core / Configuration layer.

Single source of truth for "where does this app's persistent data live on
disk". Kept separate from database/db.py (which only knows how to talk to
SQLAlchemy/SQLite) so that database path, app-data path, logs path, and
backup path are each resolved in one place and are not hard-coded into
business logic or tied to a developer's machine.

── Why this file exists ────────────────────────────────────────────────
The previous logic computed the database path as a fixed location next to
this source file (`<app_folder>/data/hr.db`). That is fine when running
from source, but breaks for the packaged Windows .exe:

  - PyInstaller's `onedir` build (see build.spec) extracts/installs the
    app into a single folder, and `sys._MEIPASS` for a onedir build is
    that same install folder.
  - If a user (or an installer) places that folder under
    `C:\\Program Files\\...`, a standard Windows user account has NO
    write permission there. SQLite then fails to create/open the .db
    file (or fails on first write), and — worse — some setups silently
    let the app create the DB in a temp/staging location that changes or
    gets wiped between runs, which looks like "my data disappeared".

The fix: for a frozen (packaged) build, store the database (and future
logs/backups) under the current user's writable per-user data directory
(`%LOCALAPPDATA%` on Windows), not next to the installed program.

── Backward compatibility ──────────────────────────────────────────────
To avoid silently orphaning an existing installation's data:
  1. Running from source (not frozen) keeps the original behaviour
     unchanged: `<project_root>/data/hr.db`. This does not affect any
     developer's local setup.
  2. A frozen build first checks whether the *old* next-to-the-exe
     location already has a database AND that location is writable. If
     so, it keeps using it (covers anyone who already installed to a
     writable folder, e.g. Desktop/a portable folder — nothing moves).
  3. Otherwise (fresh install, or the old location isn't writable — the
     Program Files case) it uses the per-user app-data directory,
     creating it if needed.

No file is ever moved or deleted by this module. If a future developer
wants to *migrate* an existing DB from the old location to the new one,
that is a deliberate, separate decision — not made silently here.
"""
import os
import sys

APP_NAME = "TURF_HR_Pro"


def is_frozen() -> bool:
    """True when running as a PyInstaller-packaged .exe."""
    return bool(getattr(sys, "frozen", False))


def _project_root() -> str:
    """Root of the source tree (parent of the `database` package)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _legacy_data_dir() -> str:
    """The pre-existing 'next to the app' data folder.

    - Frozen: next to the install folder that contains the .exe
      (`sys._MEIPASS` for a onedir build), i.e. what previously served
      as the database location.
    - Source: unchanged, `<project_root>/data`.
    """
    if is_frozen():
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = _project_root()
    return os.path.join(base, "data")


def _is_writable_dir(path: str) -> bool:
    """Best-effort check: can this process create/write files here?"""
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_test")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def _per_user_app_data_dir() -> str:
    """Writable per-user directory for this app's data, independent of
    where the program itself is installed.

    Windows: %LOCALAPPDATA%\\TURF_HR_Pro
    macOS/Linux (dev machines / non-Windows testing only — the shipped
    product targets Windows): ~/.turf_hr_pro
    """
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return os.path.join(local_app_data, APP_NAME)
    return os.path.join(os.path.expanduser("~"), f".{APP_NAME.lower()}")


def get_app_data_dir() -> str:
    """Resolve the directory the app should read/write persistent data in.

    See module docstring for the precedence rules (source vs frozen,
    legacy-location backward compatibility).
    """
    if not is_frozen():
        return _legacy_data_dir()

    legacy = _legacy_data_dir()
    legacy_db = os.path.join(legacy, "hr.db")
    if os.path.exists(legacy_db) and _is_writable_dir(legacy):
        return legacy

    per_user = _per_user_app_data_dir()
    os.makedirs(per_user, exist_ok=True)
    return per_user


def get_db_path() -> str:
    """
    Resolve the SQLite database file path.

    Checks the TURF_HR_PRO_DB_PATH environment variable first — purely
    additive, does not change default behavior for anyone who doesn't
    set it. This exists so the Phase 4A test suite (tests/) can point at
    an isolated temporary database file instead of ever touching the
    real per-installation database, without needing to duplicate or
    monkeypatch this path-resolution logic. See tests/conftest.py.
    """
    override = os.environ.get("TURF_HR_PRO_DB_PATH")
    if override:
        parent = os.path.dirname(override)
        if parent:
            os.makedirs(parent, exist_ok=True)
        return override

    data_dir = get_app_data_dir()
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "hr.db")


def get_logs_dir() -> str:
    """Not wired up to a logger yet — reserved so a future logging system
    has a stable, correct-by-construction location to write to instead of
    inventing its own (possibly Program-Files-relative) path."""
    path = os.path.join(get_app_data_dir(), "logs")
    os.makedirs(path, exist_ok=True)
    return path


def get_backup_dir() -> str:
    """Not wired up to a backup system yet — reserved for the same reason
    as get_logs_dir() above."""
    path = os.path.join(get_app_data_dir(), "backups")
    os.makedirs(path, exist_ok=True)
    return path


def get_downloads_dir() -> str:
    """Resolve the current user's real Downloads folder — used by
    services/excel_export.py so a generated report always lands
    somewhere the user can actually find it.

    Deliberately NEVER the process's current working directory (which,
    for the packaged .exe, can be anywhere a shortcut happens to launch
    it from) and NEVER the app's own install folder (e.g. Program
    Files, which a standard Windows user account cannot write to).

    Windows: reads the *actual* Downloads folder from the registry
    ("shell folders"), since it can be relocated by the user or an IT
    policy and isn't always `<home>\\Downloads`. Falls back to
    `<home>\\Downloads` if that lookup fails for any reason.
    macOS/Linux (dev machines / non-Windows testing only — the shipped
    product targets Windows): `~/Downloads`.

    If the resolved folder can't be created or written to for any
    reason, falls back to a "Downloads" subfolder of this app's own
    writable per-user data directory (see get_app_data_dir()) — still
    never CWD, never Program Files.
    """
    downloads = None
    if sys.platform.startswith("win"):
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
            ) as key:
                downloads, _ = winreg.QueryValueEx(
                    key, "{374DE290-123F-4565-9164-39C4925E467B}"
                )
        except OSError:
            downloads = None

    if not downloads:
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")

    if _is_writable_dir(downloads):
        return downloads

    fallback = os.path.join(get_app_data_dir(), "Downloads")
    os.makedirs(fallback, exist_ok=True)
    return fallback
